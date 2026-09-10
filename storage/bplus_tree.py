# storage/bplus_tree.py
import struct
from typing import List, Tuple, Any, Optional
from storage.buffer import BufferPool
from storage.page import Page

# 节点标志
NODE_TYPE_INTERNAL = 0
NODE_TYPE_LEAF = 1

HEADER_FORMAT = "=BBhii"  # is_leaf(B), num_keys(B), parent_id(h), next_id(i), prev_id(i)
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # 1 + 1 + 2 + 4 + 4 = 12 字节


def _compare_keys(k1: Any, k2: Any) -> int:
    """比较两个键的大小 (-1, 0, 1)"""
    # 数值化比较
    try:
        n1 = float(k1) if not isinstance(k1, str) or k1.isdigit() else k1
        n2 = float(k2) if not isinstance(k2, str) or k2.isdigit() else k2
        if isinstance(n1, (int, float)) and isinstance(n2, (int, float)):
            return -1 if n1 < n2 else (1 if n1 > n2 else 0)
    except Exception:
        pass
    s1 = str(k1)
    s2 = str(k2)
    return -1 if s1 < s2 else (1 if s1 > s2 else 0)


class BPlusTreeNode:
    """
    4KB 页面上的 B+ 树节点封装。
    支持内存反序列化和定长/变长二进制写入。
    """

    def __init__(self, page: Page):
        self.page = page
        self.is_leaf: int = 1
        self.num_keys: int = 0
        self.parent_id: int = -1
        self.next_id: int = -1
        self.prev_id: int = -1

        # 内存中维护的有序列表：
        # 叶子节点: keys = [k1, k2, ...], values = [(pid1, slot1), (pid2, slot2), ...]
        # 内部节点: keys = [k1, k2, ...], children = [c0, c1, c2, ...] (len(children) == len(keys) + 1)
        self.keys: List[Any] = []
        self.values: List[Tuple[int, int]] = []
        self.children: List[int] = []

        self._load()

    def _load(self):
        """从页面二进制字节流加载节点数据"""
        data = self.page.data
        if len(data) < HEADER_SIZE:
            return

        self.is_leaf, self.num_keys, self.parent_id, self.next_id, self.prev_id = struct.unpack_from(
            HEADER_FORMAT, data, 0
        )

        offset = HEADER_SIZE
        self.keys = []
        self.values = []
        self.children = []

        if self.num_keys <= 0 or self.num_keys > 250:
            self.num_keys = 0
            return

        if self.is_leaf == NODE_TYPE_LEAF:
            for _ in range(self.num_keys):
                ktype = data[offset]
                offset += 1
                if ktype == 0:  # INT / BIGINT
                    key = struct.unpack_from("=q", data, offset)[0]
                    offset += 8
                else:  # STR
                    slen = struct.unpack_from("=H", data, offset)[0]
                    offset += 2
                    key = data[offset:offset + slen].decode("utf-8", errors="replace")
                    offset += slen

                pid, slot = struct.unpack_from("=ii", data, offset)
                offset += 8
                self.keys.append(key)
                self.values.append((pid, slot))
        else:
            # 内部节点: children[0], then key[0], children[1], key[1]...
            c0 = struct.unpack_from("=i", data, offset)[0]
            offset += 4
            self.children.append(c0)

            for _ in range(self.num_keys):
                ktype = data[offset]
                offset += 1
                if ktype == 0:
                    key = struct.unpack_from("=q", data, offset)[0]
                    offset += 8
                else:
                    slen = struct.unpack_from("=H", data, offset)[0]
                    offset += 2
                    key = data[offset:offset + slen].decode("utf-8", errors="replace")
                    offset += slen

                c = struct.unpack_from("=i", data, offset)[0]
                offset += 4
                self.keys.append(key)
                self.children.append(c)

    def flush(self):
        """将内存数据重新序列化写回 4KB Page"""
        data = bytearray(4096)
        self.num_keys = len(self.keys)
        struct.pack_into(
            HEADER_FORMAT, data, 0,
            self.is_leaf, self.num_keys, self.parent_id, self.next_id, self.prev_id
        )

        offset = HEADER_SIZE
        if self.is_leaf == NODE_TYPE_LEAF:
            for k, (pid, slot) in zip(self.keys, self.values):
                if isinstance(k, int):
                    data[offset] = 0
                    offset += 1
                    struct.pack_into("=q", data, offset, k)
                    offset += 8
                else:
                    sbytes = str(k).encode("utf-8")
                    data[offset] = 1
                    offset += 1
                    struct.pack_into("=H", data, offset, len(sbytes))
                    offset += 2
                    data[offset:offset + len(sbytes)] = sbytes
                    offset += len(sbytes)

                struct.pack_into("=ii", data, offset, pid, slot)
                offset += 8
        else:
            if self.children:
                struct.pack_into("=i", data, offset, self.children[0])
                offset += 4

            for idx, k in enumerate(self.keys):
                if isinstance(k, int):
                    data[offset] = 0
                    offset += 1
                    struct.pack_into("=q", data, offset, k)
                    offset += 8
                else:
                    sbytes = str(k).encode("utf-8")
                    data[offset] = 1
                    offset += 1
                    struct.pack_into("=H", data, offset, len(sbytes))
                    offset += 2
                    data[offset:offset + len(sbytes)] = sbytes
                    offset += len(sbytes)

                c = self.children[idx + 1] if (idx + 1) < len(self.children) else -1
                struct.pack_into("=i", data, offset, c)
                offset += 4

        self.page.data = data
        self.page.is_dirty = True


class BPlusTree:
    """
    基于 4KB 数据页的工业级 B+ 树实现 (Page-based B+ Tree)。
    直接由 BufferPool 缓存调度，支持节点动态分裂、树高自增、双向叶子链表和范围扫描。
    """

    def __init__(self, buffer_pool: BufferPool, root_page_id: int, max_keys: int = 32):
        self.buffer_pool = buffer_pool
        self.root_page_id = root_page_id
        self.max_keys = max_keys

    @classmethod
    def create(cls, buffer_pool: BufferPool, max_keys: int = 32) -> "BPlusTree":
        """在表空间中分配一个新页并初始化为空 B+ 树"""
        page = buffer_pool.allocate_page()
        node = BPlusTreeNode(page)
        node.is_leaf = NODE_TYPE_LEAF
        node.num_keys = 0
        node.parent_id = -1
        node.next_id = -1
        node.prev_id = -1
        node.flush()
        buffer_pool.flush_page(page.page_id)
        return cls(buffer_pool, page.page_id, max_keys=max_keys)

    def _get_node(self, page_id: int) -> BPlusTreeNode:
        page = self.buffer_pool.get_page(page_id)
        if not page:
            raise Exception(f"Cannot load B+ tree page {page_id}")
        return BPlusTreeNode(page)

    # ---------- 查找 (Search) ----------

    def search(self, key: Any) -> List[Tuple[int, int]]:
        """
        点查：从根节点二分路由至叶子节点，返回所有匹配该 Key 的 RID (page_id, slot_id)。
        时间复杂度: O(log N)
        """
        leaf = self._find_leaf_node(key)
        results = []
        for k, rid in zip(leaf.keys, leaf.values):
            if _compare_keys(k, key) == 0:
                results.append(rid)
        return results

    def _find_leaf_node(self, key: Any) -> BPlusTreeNode:
        """从根节点自顶向下路由寻址，直至命中目标叶子节点"""
        curr = self._get_node(self.root_page_id)
        while curr.is_leaf == NODE_TYPE_INTERNAL:
            # 二分或顺序寻找路由子节点
            chosen_child = curr.children[-1]
            for idx, k in enumerate(curr.keys):
                if _compare_keys(key, k) < 0:
                    chosen_child = curr.children[idx]
                    break
            curr = self._get_node(chosen_child)
        return curr

    # ---------- 插入 (Insert) 与分裂 (Split) ----------

    def insert(self, key: Any, page_id: int, slot_id: int):
        """插入一条索引条目 (key, RID)"""
        leaf = self._find_leaf_node(key)

        # 保持键有序插入
        insert_idx = len(leaf.keys)
        for idx, k in enumerate(leaf.keys):
            if _compare_keys(key, k) < 0:
                insert_idx = idx
                break

        leaf.keys.insert(insert_idx, key)
        leaf.values.insert(insert_idx, (page_id, slot_id))

        if len(leaf.keys) > self.max_keys:
            self._split_leaf(leaf)
        else:
            leaf.flush()

    def _split_leaf(self, leaf: BPlusTreeNode):
        """叶子节点分裂 (50/50 分裂并维持双向链表)"""
        new_page = self.buffer_pool.allocate_page()
        new_leaf = BPlusTreeNode(new_page)
        new_leaf.is_leaf = NODE_TYPE_LEAF

        mid = len(leaf.keys) // 2

        new_leaf.keys = leaf.keys[mid:]
        new_leaf.values = leaf.values[mid:]
        leaf.keys = leaf.keys[:mid]
        leaf.values = leaf.values[:mid]

        # 维护双向链表指针
        new_leaf.next_id = leaf.next_id
        new_leaf.prev_id = leaf.page.page_id
        leaf.next_id = new_leaf.page.page_id

        if new_leaf.next_id != -1:
            next_node = self._get_node(new_leaf.next_id)
            next_node.prev_id = new_leaf.page.page_id
            next_node.flush()

        new_leaf.parent_id = leaf.parent_id

        # 向上推的键是新叶子的第一个键
        split_key = new_leaf.keys[0]

        leaf.flush()
        new_leaf.flush()

        self._insert_into_parent(leaf, split_key, new_leaf)

    def _split_internal(self, node: BPlusTreeNode):
        """内部节点分裂 (中位数提升到父节点)"""
        new_page = self.buffer_pool.allocate_page()
        new_node = BPlusTreeNode(new_page)
        new_node.is_leaf = NODE_TYPE_INTERNAL

        mid = len(node.keys) // 2
        promote_key = node.keys[mid]

        new_node.keys = node.keys[mid + 1:]
        new_node.children = node.children[mid + 1:]

        node.keys = node.keys[:mid]
        node.children = node.children[:mid + 1]

        new_node.parent_id = node.parent_id

        # 更新新子节点的 parent 指针
        for cid in new_node.children:
            child = self._get_node(cid)
            child.parent_id = new_node.page.page_id
            child.flush()

        node.flush()
        new_node.flush()

        self._insert_into_parent(node, promote_key, new_node)

    def _insert_into_parent(self, left: BPlusTreeNode, key: Any, right: BPlusTreeNode):
        """将中位数键及右孩子指针插入父节点"""
        if left.parent_id == -1 or left.page.page_id == self.root_page_id:
            # 根节点分裂 -> 产生新的根节点 (树高 +1)
            new_root_page = self.buffer_pool.allocate_page()
            new_root = BPlusTreeNode(new_root_page)
            new_root.is_leaf = NODE_TYPE_INTERNAL
            new_root.keys = [key]
            new_root.children = [left.page.page_id, right.page.page_id]
            new_root.parent_id = -1

            left.parent_id = new_root_page.page_id
            right.parent_id = new_root_page.page_id

            new_root.flush()
            left.flush()
            right.flush()

            self.root_page_id = new_root_page.page_id
            return

        parent = self._get_node(left.parent_id)
        insert_idx = len(parent.keys)
        for idx, k in enumerate(parent.keys):
            if _compare_keys(key, k) < 0:
                insert_idx = idx
                break

        parent.keys.insert(insert_idx, key)
        parent.children.insert(insert_idx + 1, right.page.page_id)
        right.parent_id = parent.page.page_id

        if len(parent.keys) > self.max_keys:
            self._split_internal(parent)
        else:
            parent.flush()

    # ---------- 范围扫描 (Range Scan) ----------

    def range_scan(self, low_key: Any = None, high_key: Any = None) -> List[Tuple[Any, Tuple[int, int]]]:
        """
        范围查询：沿叶子链表高效顺序推进。
        返回: [(key, (page_id, slot_id)), ...]
        """
        if low_key is not None:
            curr = self._find_leaf_node(low_key)
        else:
            # 定位到最左侧叶子节点
            curr = self._get_node(self.root_page_id)
            while curr.is_leaf == NODE_TYPE_INTERNAL:
                curr = self._get_node(curr.children[0])

        results = []
        while curr:
            for k, rid in zip(curr.keys, curr.values):
                if low_key is not None and _compare_keys(k, low_key) < 0:
                    continue
                if high_key is not None and _compare_keys(k, high_key) > 0:
                    return results
                results.append((k, rid))

            if curr.next_id != -1:
                curr = self._get_node(curr.next_id)
            else:
                break

        return results

    # ---------- 删除 (Delete) ----------

    def delete(self, key: Any, page_id: int, slot_id: int) -> bool:
        """删除指定键及 RID"""
        leaf = self._find_leaf_node(key)
        found = False
        new_keys = []
        new_vals = []
        for k, rid in zip(leaf.keys, leaf.values):
            if not found and _compare_keys(k, key) == 0 and rid == (page_id, slot_id):
                found = True
                continue
            new_keys.append(k)
            new_vals.append(rid)

        if found:
            leaf.keys = new_keys
            leaf.values = new_vals
            leaf.flush()
        return found
