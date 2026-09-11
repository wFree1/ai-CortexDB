import os
import json
import struct
from typing import Dict, List, Any, Optional, Tuple
from storage.buffer import BufferPool
from storage.page import PageManager, Page


from storage.bplus_tree import BPlusTree

def _normalize_type(typ_str: str) -> str:
    t = (typ_str or "").strip().upper()
    if "(" in t:
        t = t.split("(", 1)[0].strip()
    return t

class FileManager:
    def __init__(self, data_dir: str = 'data'):
        self.data_dir = data_dir
        self.page_manager = PageManager(self.data_dir)
        self.buffer_pool = BufferPool(self.page_manager)

        # 表文件映射: {table_name: [header_page_id, data_page_id_1, data_page_id_2, ...]}
        self.table_files: Dict[str, List[int]] = {}
        self._load_table_files()

        # B+ 树索引实例与元数据缓存: {table_name: {col_name: BPlusTree}}
        self.trees: Dict[str, Dict[str, BPlusTree]] = {}
        self.index_roots: Dict[str, Dict[str, int]] = {}
        self._load_index_roots()

    def _load_index_roots(self):
        idx_file = os.path.join(self.data_dir, 'index_roots.json')
        if os.path.exists(idx_file):
            try:
                with open(idx_file, 'r', encoding='utf-8') as f:
                    self.index_roots = json.load(f)
                for tbl, col_roots in self.index_roots.items():
                    for col, rpid in col_roots.items():
                        self.trees.setdefault(tbl, {})[col] = BPlusTree(self.buffer_pool, rpid)
            except Exception:
                pass

    def _save_index_roots(self):
        idx_file = os.path.join(self.data_dir, 'index_roots.json')
        os.makedirs(self.data_dir, exist_ok=True)
        with open(idx_file, 'w', encoding='utf-8') as f:
            json.dump(self.index_roots, f, indent=2)

    def get_bplus_tree(self, table_name: str, col_name: str) -> Optional[BPlusTree]:
        """获取指定表在某列上的 B+ 树索引实例"""
        return self.trees.get(table_name, {}).get(col_name)

    def create_index(self, table_name: str, col_name: str) -> BPlusTree:
        """为指定表和列构建全新 4KB Page B+ 树索引，并填充已有数据"""
        tree = BPlusTree.create(self.buffer_pool)
        self.trees.setdefault(table_name, {})[col_name] = tree
        self.index_roots.setdefault(table_name, {})[col_name] = tree.root_page_id
        self._save_index_roots()

        # 若已有记录，填充进索引树
        header_page = self._get_table_header(table_name)
        if header_page:
            try:
                columns = self._get_column_info_from_header(header_page)
                current_page_id = header_page.get_int(4)
                while current_page_id != -1:
                    page = self.buffer_pool.get_page(current_page_id)
                    if not page:
                        break
                    record_count = page.get_int(0)
                    next_page_id = page.get_int(4)
                    data_offset = 8
                    for _ in range(record_count):
                        try:
                            record, new_offset = self._deserialize_record(page.data, columns, data_offset)
                            if col_name in record:
                                tree.insert(record[col_name], current_page_id, data_offset)
                            data_offset = new_offset
                        except Exception:
                            break
                    current_page_id = next_page_id
            except Exception:
                pass

        return tree

    def _load_table_files(self):
        mapping_file = os.path.join(self.data_dir, 'table_files.json')
        if os.path.exists(mapping_file):
            with open(mapping_file, 'r') as f:
                self.table_files = json.load(f)

    def _save_table_files(self):
        mapping_file = os.path.join(self.data_dir, 'table_files.json')
        os.makedirs(self.data_dir, exist_ok=True)
        with open(mapping_file, 'w') as f:
            json.dump(self.table_files, f, indent=2)

    def create_table_file(self, table_name: str, columns: List[Dict[str, str]], primary_key: Optional[str] = None) -> List[int]:
        """为表创建初始页面，并在页头存储表结构；若存在主键则自动构建 B+ 树主键索引"""
        if table_name in self.table_files:
            raise Exception(f"Table file for '{table_name}' already exists")

        # 分配一个页面用于存储表头信息
        header_page = self.buffer_pool.allocate_page()

        # 初始化表头
        # offset 0: 记录数 (4 bytes)
        header_page.set_int(0, 0)
        # offset 4: 第一个数据页面ID (4 bytes), 初始化为-1表示无数据页
        header_page.set_int(4, -1)
        # offset 8: 下一个页面ID (4 bytes), 用于链接页，初始化为-1
        header_page.set_int(8, -1)

        # 从 offset 12 开始存储列信息
        # 先存储列数 (4 bytes)
        column_count_offset = 12
        header_page.set_int(column_count_offset, len(columns))

        # 然后依次存储每列的信息: 列名长度(2 bytes) + 列名 + 列类型长度(2 bytes) + 列类型
        current_offset = column_count_offset + 4
        for col in columns:
            col_name = col['name']
            col_type = col['type']

            # 写入列名长度和列名
            name_bytes = col_name.encode('utf-8')
            header_page.set_int(current_offset, len(name_bytes), size=2)  # 2 bytes for length
            current_offset += 2
            header_page.write_data(current_offset, name_bytes)
            current_offset += len(name_bytes)

            # 写入列类型长度和列类型
            type_bytes = col_type.encode('utf-8')
            header_page.set_int(current_offset, len(type_bytes), size=2)
            current_offset += 2
            header_page.write_data(current_offset, type_bytes)
            current_offset += len(type_bytes)

        # 确保表头页写入磁盘
        self.buffer_pool.flush_page(header_page.page_id)

        self.table_files[table_name] = [header_page.page_id]
        self._save_table_files()

        if primary_key:
            self.create_index(table_name, primary_key)

        return self.table_files[table_name]

    def get_table_pages(self, table_name: str) -> Optional[List[int]]:
        """获取表的所有页面ID，包括表头页"""
        return self.table_files.get(table_name)

    def _get_table_header(self, table_name: str) -> Optional[Page]:
        """获取表的头页面"""
        page_ids = self.get_table_pages(table_name)
        if not page_ids or len(page_ids) == 0:
            return None
        return self.buffer_pool.get_page(page_ids[0])

    def _get_column_info_from_header(self, header_page: Page) -> List[Dict[str, str]]:
        """从表头页解析出列信息"""
        columns = []
        # 读取列数
        column_count = header_page.get_int(12)
        current_offset = 16  # 12 + 4

        for _ in range(column_count):
            # 读取列名
            name_len = header_page.get_int(current_offset, size=2)
            current_offset += 2
            col_name = header_page.read_data(current_offset, name_len).decode('utf-8')
            current_offset += name_len

            # 读取列类型
            type_len = header_page.get_int(current_offset, size=2)
            current_offset += 2
            col_type = header_page.read_data(current_offset, type_len).decode('utf-8')
            current_offset += type_len

            columns.append({'name': col_name, 'type': col_type})

        return columns

    def _serialize_record(self, record: Dict[str, Any], columns: List[Dict[str, str]]) -> bytes:
        """将记录序列化为字节流（支持全部工业级数据类型及 NULL 标志）"""
        serialized_data = bytearray()
        for col in columns:
            col_name = col['name']
            col_type = _normalize_type(col['type'])
            value = record.get(col_name)

            # NULL 检查与标志位: 0 为 NULL, 1 为非 NULL
            if value is None:
                serialized_data.append(0)
                continue
            serialized_data.append(1)

            if col_type in ('INT', 'INTEGER'):
                serialized_data.extend(struct.pack('=i', int(value)))
            elif col_type == 'BIGINT':
                serialized_data.extend(struct.pack('=q', int(value)))
            elif col_type == 'SMALLINT':
                serialized_data.extend(struct.pack('=h', int(value)))
            elif col_type == 'TINYINT':
                serialized_data.extend(struct.pack('=b', int(value)))
            elif col_type in ('FLOAT', 'REAL'):
                serialized_data.extend(struct.pack('=f', float(value)))
            elif col_type == 'DOUBLE':
                serialized_data.extend(struct.pack('=d', float(value)))
            elif col_type in ('BOOL', 'BOOLEAN'):
                if isinstance(value, str):
                    b_val = 1 if value.strip().upper() in ('TRUE', '1', 'T') else 0
                else:
                    b_val = 1 if bool(value) else 0
                serialized_data.extend(struct.pack('=b', b_val))
            elif col_type in ('VARCHAR', 'CHAR', 'TEXT', 'DATE', 'DATETIME', 'TIMESTAMP', 'TIME', 'DECIMAL', 'NUMERIC'):
                encoded_str = str(value).encode('utf-8')
                serialized_data.extend(struct.pack('=i', len(encoded_str)))
                serialized_data.extend(encoded_str)
            elif col_type in ('BLOB', 'BYTES'):
                raw_bytes = value if isinstance(value, (bytes, bytearray)) else str(value).encode('utf-8')
                serialized_data.extend(struct.pack('=i', len(raw_bytes)))
                serialized_data.extend(raw_bytes)
            else:
                encoded_str = str(value).encode('utf-8')
                serialized_data.extend(struct.pack('=i', len(encoded_str)))
                serialized_data.extend(encoded_str)

        return bytes(serialized_data)

    def _deserialize_record(self, data: bytes, columns: List[Dict[str, str]], offset: int = 0) -> Tuple[Dict[str, Any], int]:
        """从字节流反序列化记录，返回记录和新的偏移量"""
        record = {}
        current_offset = offset
        for col in columns:
            col_name = col['name']
            col_type = _normalize_type(col['type'])

            # 读取 1 字节 NULL 标志位
            is_not_null = data[current_offset]
            current_offset += 1

            if is_not_null == 0:
                record[col_name] = None
                continue

            if col_type in ('INT', 'INTEGER'):
                value = struct.unpack_from('=i', data, current_offset)[0]
                current_offset += 4
            elif col_type == 'BIGINT':
                value = struct.unpack_from('=q', data, current_offset)[0]
                current_offset += 8
            elif col_type == 'SMALLINT':
                value = struct.unpack_from('=h', data, current_offset)[0]
                current_offset += 2
            elif col_type == 'TINYINT':
                value = struct.unpack_from('=b', data, current_offset)[0]
                current_offset += 1
            elif col_type in ('FLOAT', 'REAL'):
                value = round(struct.unpack_from('=f', data, current_offset)[0], 6)
                current_offset += 4
            elif col_type == 'DOUBLE':
                value = struct.unpack_from('=d', data, current_offset)[0]
                current_offset += 8
            elif col_type in ('BOOL', 'BOOLEAN'):
                value = bool(struct.unpack_from('=b', data, current_offset)[0])
                current_offset += 1
            elif col_type in ('VARCHAR', 'CHAR', 'TEXT', 'DATE', 'DATETIME', 'TIMESTAMP', 'TIME'):
                str_len = struct.unpack_from('=i', data, current_offset)[0]
                current_offset += 4
                value = data[current_offset:current_offset + str_len].decode('utf-8', errors='replace')
                current_offset += str_len
            elif col_type in ('DECIMAL', 'NUMERIC'):
                str_len = struct.unpack_from('=i', data, current_offset)[0]
                current_offset += 4
                raw_str = data[current_offset:current_offset + str_len].decode('utf-8', errors='replace')
                current_offset += str_len
                try:
                    value = float(raw_str)
                except Exception:
                    value = raw_str
            elif col_type in ('BLOB', 'BYTES'):
                b_len = struct.unpack_from('=i', data, current_offset)[0]
                current_offset += 4
                value = bytes(data[current_offset:current_offset + b_len])
                current_offset += b_len
            else:
                str_len = struct.unpack_from('=i', data, current_offset)[0]
                current_offset += 4
                value = data[current_offset:current_offset + str_len].decode('utf-8', errors='replace')
                current_offset += str_len

            record[col_name] = value

        return record, current_offset

    def _get_record_size(self, columns: List[Dict[str, str]]) -> int:
        """计算一条记录的最大预估大小"""
        size = 0
        for col in columns:
            col_type = _normalize_type(col['type'])
            size += 1  # null flag
            if col_type in ('INT', 'INTEGER', 'FLOAT', 'REAL'):
                size += 4
            elif col_type in ('BIGINT', 'DOUBLE'):
                size += 8
            elif col_type == 'SMALLINT':
                size += 2
            elif col_type in ('TINYINT', 'BOOL', 'BOOLEAN'):
                size += 1
            else:
                size += 4 + 255
        return size

    def insert_record(self, table_name: str, record: Dict[str, Any]) -> bool:
        """将一条记录插入到表中"""
        header_page = self._get_table_header(table_name)
        if not header_page:
            raise Exception(f"Table '{table_name}' does not exist")

        columns = self._get_column_info_from_header(header_page)
        record_data = self._serialize_record(record, columns)
        actual_record_size = len(record_data)  # 使用实际序列化后的大小

        # 获取第一个数据页ID
        first_data_page_id = header_page.get_int(4)

        target_page_id = -1
        target_page = None
        free_space_offset = -1

        if first_data_page_id == -1:
            # 没有数据页，分配一个新的
            new_data_page = self.buffer_pool.allocate_page()
            # 初始化数据页：offset 0 存储本页记录数，offset 4 存储下一个页ID
            new_data_page.set_int(0, 0)  # 当前页记录数
            new_data_page.set_int(4, -1)  # 下一个页ID
            # 从 offset 8 开始存储数据
            free_space_offset = 8
            target_page = new_data_page
            target_page_id = new_page_id = new_data_page.page_id

            # 更新表头，指向新的数据页
            header_page.set_int(4, new_page_id)
            self.buffer_pool.flush_page(header_page.page_id)
            # 更新表文件映射
            self.table_files[table_name].append(new_page_id)
            self._save_table_files()
        else:
            # 遍历数据页链表，寻找有空闲空间的页
            current_page_id = first_data_page_id
            while current_page_id != -1:
                page = self.buffer_pool.get_page(current_page_id)
                if not page:
                    break

                record_count = page.get_int(0)
                next_page_id = page.get_int(4)

                # 精确计算当前页的写入偏移量
                current_offset = 8  # 跳过页头 (记录数4字节 + 下一页ID4字节)
                valid_record_count = 0  # 用于计数成功反序列化的记录

                for _ in range(record_count):
                    try:
                        _, next_offset = self._deserialize_record(page.data, columns, current_offset)
                        current_offset = next_offset
                        valid_record_count += 1
                    except Exception as e:
                        print(
                            f"Warning: Skipping corrupted record in page {current_page_id} at offset {current_offset}: {e}")
                        # 如果反序列化失败，我们跳过这条记录，但为了安全，我们中断当前页的插入，转而寻找新页。
                        # 这是一种保守策略，避免在损坏的页上继续写入。
                        break

                # 检查剩余空间是否足够
                if current_offset + actual_record_size <= 4096:  # PAGE_SIZE
                    free_space_offset = current_offset
                    target_page = page
                    target_page_id = current_page_id
                    # 更新页内记录数为有效记录数
                    page.set_int(0, valid_record_count)
                    break
                else:
                    # 空间不足，继续查找下一页
                    pass

                current_page_id = next_page_id

            if target_page_id == -1:
                # 所有现有页都满了，分配新页
                new_data_page = self.buffer_pool.allocate_page()
                new_data_page.set_int(0, 0)
                new_data_page.set_int(4, -1)
                free_space_offset = 8
                target_page = new_data_page
                target_page_id = new_page_id = new_data_page.page_id

                # 将新页链接到链表末尾
                current_page_id = first_data_page_id
                while True:
                    page = self.buffer_pool.get_page(current_page_id)
                    if page.get_int(4) == -1:
                        page.set_int(4, new_page_id)
                        self.buffer_pool.flush_page(current_page_id)
                        break
                    current_page_id = page.get_int(4)

                # 更新表文件映射
                self.table_files[table_name].append(new_page_id)
                self._save_table_files()

        # 写入记录
        target_page.write_data(free_space_offset, record_data)
        # 更新页内记录数
        target_page.set_int(0, target_page.get_int(0) + 1)
        # 标记为脏页，BufferPool会在LRU淘汰或显式flush时写回磁盘

        # 更新表头的总记录数
        total_count = header_page.get_int(0)
        header_page.set_int(0, total_count + 1)
        self.buffer_pool.flush_page(header_page.page_id)

        # 同步更新该表的所有 B+ 树索引
        if table_name in self.trees:
            for col_name, tree in self.trees[table_name].items():
                if col_name in record:
                    tree.insert(record[col_name], target_page_id, free_space_offset)

        return True

    def read_records(self, table_name: str, condition: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """读取表中的所有记录，并根据条件过滤"""
        header_page = self._get_table_header(table_name)
        if not header_page:
            raise Exception(f"Table '{table_name}' does not exist")

        columns = self._get_column_info_from_header(header_page)

        results = []
        current_page_id = header_page.get_int(4)  # 第一个数据页ID

        while current_page_id != -1:
            page = self.buffer_pool.get_page(current_page_id)
            if not page:
                break

            record_count = page.get_int(0)
            next_page_id = page.get_int(4)

            # 从 offset 8 开始读取记录
            data_offset = 8
            for _ in range(record_count):
                try:
                    record, new_offset = self._deserialize_record(page.data, columns, data_offset)

                    # 应用条件过滤
                    if condition is None or self._evaluate_condition_in_fm(record, condition):
                        results.append(record)
                    data_offset = new_offset
                except Exception as e:
                    print(f"Error deserializing record: {e}")
                    break

            current_page_id = next_page_id

        return results

    def read_records_via_index(self, table_name: str, col_name: str, key_val: Any, op: str = "=") -> List[Dict[str, Any]]:
        """利用 B+ 树索引以 O(log N) 快速查找满足条件的记录"""
        tree = self.get_bplus_tree(table_name, col_name)
        if not tree:
            cond = {
                "left": {"type": "column", "value": col_name},
                "operator": op,
                "right": {"type": "constant", "value": key_val}
            }
            return self.read_records(table_name, cond)

        header_page = self._get_table_header(table_name)
        if not header_page:
            raise Exception(f"Table '{table_name}' does not exist")
        columns = self._get_column_info_from_header(header_page)

        from storage.bplus_tree import _compare_keys
        rids: List[Tuple[int, int]] = []
        if op == "=":
            rids = tree.search(key_val)
        elif op == ">":
            items = tree.range_scan(key_val, None)
            rids = [rid for k, rid in items if _compare_keys(k, key_val) > 0]
        elif op == ">=":
            items = tree.range_scan(key_val, None)
            rids = [rid for k, rid in items]
        elif op == "<":
            items = tree.range_scan(None, key_val)
            rids = [rid for k, rid in items if _compare_keys(k, key_val) < 0]
        elif op == "<=":
            items = tree.range_scan(None, key_val)
            rids = [rid for k, rid in items]
        else:
            cond = {
                "left": {"type": "column", "value": col_name},
                "operator": op,
                "right": {"type": "constant", "value": key_val}
            }
            return self.read_records(table_name, cond)

        results = []
        for page_id, offset in rids:
            page = self.buffer_pool.get_page(page_id)
            if not page:
                continue
            try:
                rec, _ = self._deserialize_record(page.data, columns, offset)
                results.append(rec)
            except Exception as e:
                pass
        return results

    def rebuild_indexes(self, table_name: str):
        """重新扫描数据页，重建该表的所有 B+ 树索引"""
        if table_name not in self.trees or not self.trees[table_name]:
            return
        header_page = self._get_table_header(table_name)
        if not header_page:
            return
        columns = self._get_column_info_from_header(header_page)

        indexed_cols = list(self.trees[table_name].keys())
        for col_name in indexed_cols:
            tree = BPlusTree.create(self.buffer_pool)
            self.trees[table_name][col_name] = tree
            self.index_roots.setdefault(table_name, {})[col_name] = tree.root_page_id

        self._save_index_roots()

        current_page_id = header_page.get_int(4)
        while current_page_id != -1:
            page = self.buffer_pool.get_page(current_page_id)
            if not page:
                break
            record_count = page.get_int(0)
            next_page_id = page.get_int(4)
            data_offset = 8
            for _ in range(record_count):
                try:
                    record, new_offset = self._deserialize_record(page.data, columns, data_offset)
                    for col_name in indexed_cols:
                        if col_name in record:
                            self.trees[table_name][col_name].insert(record[col_name], current_page_id, data_offset)
                    data_offset = new_offset
                except Exception:
                    break
            current_page_id = next_page_id

    def _evaluate_condition_in_fm(self, record: Dict[str, Any], condition: Any) -> bool:
        """在FileManager内部评估条件（支持 =, !=, <>, >, <, >=, <=, LIKE, IN, BETWEEN, IS, IS NOT, compound, 以及 SQL 字符串条件）"""
        if not condition:
            return True

        if isinstance(condition, str):
            from engine.executor import _evaluate_condition
            return _evaluate_condition(record, condition)

        cond_type = condition.get('type')
        if cond_type == 'compound':
            op = condition.get('operator', 'AND').upper()
            children = condition.get('children', [])
            if op == 'AND':
                return all(self._evaluate_condition_in_fm(record, c) for c in children)
            elif op == 'OR':
                return any(self._evaluate_condition_in_fm(record, c) for c in children)
            elif op == 'NOT':
                return not self._evaluate_condition_in_fm(record, children[0]) if children else True

        left = condition.get('left', {})
        operator = condition.get('operator', '').upper().strip()
        right = condition.get('right', {})

        col_name = left.get('value') if left.get('type') == 'column' else None
        if not col_name:
            return True

        if '.' in col_name:
            _, col_name = col_name.split('.', 1)

        col_value = record.get(col_name)

        if operator == 'IS':
            return col_value is None
        elif operator in ('IS NOT', 'IS_NOT'):
            return col_value is not None

        if col_value is None:
            return False

        if operator in ('IN', 'NOT IN'):
            vals = right.get('value', [])
            if not isinstance(vals, (list, tuple, set)):
                vals = [vals]
            match = False
            for target in vals:
                try:
                    if str(col_value).strip() == str(target).strip() or float(col_value) == float(target):
                        match = True
                        break
                except Exception:
                    if str(col_value) == str(target):
                        match = True
                        break
            return match if operator == 'IN' else not match

        if operator in ('BETWEEN', 'NOT BETWEEN'):
            low = right.get('low')
            high = right.get('high')
            try:
                cv = float(col_value)
                lv = float(low)
                hv = float(high)
                in_range = (lv <= cv <= hv)
            except Exception:
                in_range = (str(low) <= str(col_value) <= str(high))
            return in_range if operator == 'BETWEEN' else not in_range

        if operator in ('LIKE', 'NOT LIKE'):
            pattern = str(right.get('value', ''))
            if (pattern.startswith("'") and pattern.endswith("'")) or (pattern.startswith('"') and pattern.endswith('"')):
                pattern = pattern[1:-1]
            parts = re.split(r'(%|_)', pattern)
            regex_parts = []
            for p in parts:
                if p == '%':
                    regex_parts.append('.*')
                elif p == '_':
                    regex_parts.append('.')
                else:
                    regex_parts.append(re.escape(p))
            regex_pat = '^' + ''.join(regex_parts) + '$'
            matched = bool(re.match(regex_pat, str(col_value), re.IGNORECASE | re.DOTALL))
            return matched if operator == 'LIKE' else not matched

        right_value = right.get('value')
        if isinstance(col_value, bool) or isinstance(right_value, bool) or str(right_value).strip().upper() in ('TRUE', 'FALSE'):
            cv = (str(col_value).strip().upper() == 'TRUE') if isinstance(col_value, str) else bool(col_value)
            rv = (str(right_value).strip().upper() == 'TRUE') if isinstance(right_value, str) else bool(right_value)
            if operator == '=':   return cv == rv
            elif operator in ('!=', '<>'): return cv != rv
            return False

        try:
            cv = float(col_value)
            rv = float(right_value)
            if operator == '=':   return cv == rv
            elif operator == '>':  return cv > rv
            elif operator == '<':  return cv < rv
            elif operator == '>=': return cv >= rv
            elif operator == '<=': return cv <= rv
            elif operator in ('!=', '<>'): return cv != rv
        except Exception:
            pass

        cs = str(col_value)
        rs = str(right_value)
        if operator == '=':   return cs == rs
        elif operator == '>':  return cs > rs
        elif operator == '<':  return cs < rs
        elif operator == '>=': return cs >= rs
        elif operator == '<=': return cs <= rs
        elif operator in ('!=', '<>'): return cs != rs

        return False

    def delete_records(self, table_name: str, condition: Dict[str, Any] = None) -> int:
        """删除满足条件的记录 (简化实现：物理删除并重写页)"""
        header_page = self._get_table_header(table_name)
        if not header_page:
            raise Exception(f"Table '{table_name}' does not exist")

        columns = self._get_column_info_from_header(header_page)

        deleted_count = 0
        current_page_id = header_page.get_int(4)

        while current_page_id != -1:
            page = self.buffer_pool.get_page(current_page_id)
            if not page:
                break

            record_count = page.get_int(0)
            next_page_id = page.get_int(4)

            # 读取所有记录，过滤掉要删除的
            records_to_keep = []
            data_offset = 8
            for i in range(record_count):
                record, new_offset = self._deserialize_record(page.data, columns, data_offset)
                data_offset = new_offset

                should_delete = (condition is None or self._evaluate_condition_in_fm(record, condition))
                if not should_delete:
                    # 保留不满足删除条件的记录
                    records_to_keep.append(record)
                else:
                    deleted_count += 1

            # 重写当前页
            page.set_int(0, len(records_to_keep))  # 更新页内记录数
            write_offset = 8
            for rec in records_to_keep:
                rec_data = self._serialize_record(rec, columns)
                page.write_data(write_offset, rec_data)
                write_offset += len(rec_data)

            # 填充剩余空间为0 (可选)
            page.write_data(write_offset, b'\x00' * (4096 - write_offset))

            current_page_id = next_page_id

        # 更新表头的总记录数
        total_count = header_page.get_int(0)
        header_page.set_int(0, total_count - deleted_count)
        self.buffer_pool.flush_page(header_page.page_id)

        if deleted_count > 0:
            self.rebuild_indexes(table_name)

        # 立即将内存缓冲池中被删除/修改的脏页持久化到静态数据文件 (.db)
        self.flush_all()

        return deleted_count

    def add_page_to_table(self, table_name: str, page_id: int):
        if table_name in self.table_files:
            self.table_files[table_name].append(page_id)
            self._save_table_files()

    def drop_table_file(self, table_name: str):
        if table_name in self.table_files:
            # 释放所有页面
            for page_id in self.table_files[table_name]:
                self.buffer_pool.free_page(page_id)

            del self.table_files[table_name]
            self._save_table_files()

        # 清理索引
        if table_name in self.trees:
            del self.trees[table_name]
        if table_name in self.index_roots:
            del self.index_roots[table_name]
            self._save_index_roots()

    def flush_all(self):
        self.buffer_pool.flush_all()

    def close(self):
        """刷新所有缓冲并释放资源"""
        self.flush_all()
        if hasattr(self.buffer_pool, 'close'):
            self.buffer_pool.close()
        if hasattr(self.page_manager, 'close'):
            self.page_manager.close()

    def update_records(self, table_name: str, set_clause: List[tuple], condition: Dict[str, Any] = None) -> int:
        """更新满足条件的记录"""
        header_page = self._get_table_header(table_name)
        if not header_page:
            raise Exception(f"Table '{table_name}' does not exist")

        columns = self._get_column_info_from_header(header_page)
        updated_count = 0

        # 获取第一个数据页ID
        current_page_id = header_page.get_int(4)
        while current_page_id != -1:
            page = self.buffer_pool.get_page(current_page_id)
            if not page:
                break

            record_count = page.get_int(0)
            next_page_id = page.get_int(4)

            # 读取所有记录，更新满足条件的
            records = []
            data_offset = 8
            for i in range(record_count):
                record, new_offset = self._deserialize_record(page.data, columns, data_offset)
                data_offset = new_offset

                # 判断是否满足条件
                should_update = True
                if condition is not None:
                    should_update = self._evaluate_condition_in_fm(record, condition)

                if should_update:
                    # 执行更新
                    for set_col, set_value in set_clause:
                        record[set_col] = set_value
                    updated_count += 1

                records.append(record)

            # 重写当前页
            page.set_int(0, len(records))  # 更新页内记录数
            write_offset = 8
            for rec in records:
                rec_data = self._serialize_record(rec, columns)
                page.write_data(write_offset, rec_data)
                write_offset += len(rec_data)

            # 填充剩余空间 (可选)
            if write_offset < 4096:
                page.write_data(write_offset, b'\x00' * (4096 - write_offset))

            current_page_id = next_page_id

        # 更新表头的总记录数 (这里总记录数不变，因为是更新不是增删)
        # 但我们可能需要更新一些统计信息，这里暂不处理
        if updated_count > 0:
            self.rebuild_indexes(table_name)

        # 立即将内存缓冲池中被修改的脏页持久化到静态数据文件 (.db)
        self.flush_all()

        return updated_count