# storage/sys_catalog.py
import struct
from typing import Dict, List, Any, Optional, Tuple
from storage.buffer import BufferPool
from storage.page import Page

# 系统表固定页号定义 (Fixed Page IDs for Bootstrap System Tables)
SUPERBLOCK_PAGE_ID = 0
SYS_TABLES_PAGE_ID = 1
SYS_COLUMNS_PAGE_ID = 2
SYS_INDEXES_PAGE_ID = 3

MAGIC_DSPH = b"DSPH"  # DataSphere 存储标识魔数

# 系统表的预置列定义
SYS_TABLES_COLUMNS = [
    {"name": "table_id", "type": "INT"},
    {"name": "table_name", "type": "VARCHAR"},
    {"name": "root_page", "type": "INT"},
    {"name": "primary_key", "type": "VARCHAR"},
    {"name": "row_count", "type": "INT"},
]

SYS_COLUMNS_COLUMNS = [
    {"name": "table_id", "type": "INT"},
    {"name": "col_name", "type": "VARCHAR"},
    {"name": "col_type", "type": "VARCHAR"},
    {"name": "col_order", "type": "INT"},
    {"name": "is_pk", "type": "INT"},
]

SYS_INDEXES_COLUMNS = [
    {"name": "index_name", "type": "VARCHAR"},
    {"name": "table_name", "type": "VARCHAR"},
    {"name": "col_name", "type": "VARCHAR"},
    {"name": "root_page", "type": "INT"},
    {"name": "is_unique", "type": "INT"},
]


def serialize_sys_record(record: Dict[str, Any], columns: List[Dict[str, str]]) -> bytes:
    """序列化系统表单条记录为二进制字节流"""
    buf = bytearray()
    for col in columns:
        cname = col["name"]
        ctype = col["type"]
        val = record.get(cname)
        if ctype == "INT":
            buf.extend(struct.pack("i", int(val if val is not None else 0)))
        elif ctype == "VARCHAR":
            s = str(val if val is not None else "")
            encoded = s.encode("utf-8")
            buf.extend(struct.pack("i", len(encoded)))
            buf.extend(encoded)
    return bytes(buf)


def deserialize_sys_record(data: bytes, columns: List[Dict[str, str]], offset: int) -> Tuple[Dict[str, Any], int]:
    """反序列化系统表单条记录"""
    rec = {}
    curr = offset
    for col in columns:
        cname = col["name"]
        ctype = col["type"]
        if ctype == "INT":
            rec[cname] = struct.unpack("i", data[curr:curr + 4])[0]
            curr += 4
        elif ctype == "VARCHAR":
            slen = struct.unpack("i", data[curr:curr + 4])[0]
            curr += 4
            rec[cname] = data[curr:curr + slen].decode("utf-8")
            curr += slen
    return rec, curr


class SysCatalogManager:
    """
    内核自举系统表管理器 (Bootstrap System Catalog Manager)。
    管理固定 Page 0 (Superblock)、Page 1 (sys_tables)、Page 2 (sys_columns)、Page 3 (sys_indexes)。
    在系统首次启动时自举注册自身，提供持久化的元数据二进制表读写。
    """

    def __init__(self, buffer_pool: BufferPool):
        self.buffer_pool = buffer_pool
        self._ensure_bootstrap()

    def _ensure_bootstrap(self):
        """检查 Superblock，若未初始化则自动执行内核自举 (Bootstrap)"""
        # 尝试读取 Page 0
        sb_page = self.buffer_pool.get_page(SUPERBLOCK_PAGE_ID)
        if sb_page is None or sb_page.read_data(0, 4) != MAGIC_DSPH:
            self._do_bootstrap()

    def _do_bootstrap(self):
        """执行硬编码自举，初始化 Page 0, 1, 2, 3"""
        # 1. 初始化 Page 0 (Superblock)
        sb_page = self.buffer_pool.get_page(SUPERBLOCK_PAGE_ID)
        if sb_page is None:
            sb_page = self.buffer_pool.allocate_page()  # Page 0

        sb_page.write_data(0, MAGIC_DSPH)
        sb_page.set_int(4, 1)  # Version = 1
        sb_page.set_int(8, SYS_TABLES_PAGE_ID)
        sb_page.set_int(12, SYS_COLUMNS_PAGE_ID)
        sb_page.set_int(16, SYS_INDEXES_PAGE_ID)
        sb_page.set_int(20, 100)  # Next user table_id starts at 100

        # 2. 确保 Page 1, 2, 3 被物理分配出来
        while self.buffer_pool.page_manager.tablespace.page_count < 4:
            self.buffer_pool.allocate_page()

        # 初始化系统表头 (offset 0: record_count, offset 4: next_page)
        for pid in [SYS_TABLES_PAGE_ID, SYS_COLUMNS_PAGE_ID, SYS_INDEXES_PAGE_ID]:
            page = self.buffer_pool.get_page(pid)
            if page:
                page.set_int(0, 0)
                page.set_int(4, -1)

        # 3. 将系统表自身注册进 sys_tables 与 sys_columns
        self._insert_sys_table(1, "sys_tables", SYS_TABLES_PAGE_ID, "", 3)
        self._insert_sys_table(2, "sys_columns", SYS_COLUMNS_PAGE_ID, "", 15)
        self._insert_sys_table(3, "sys_indexes", SYS_INDEXES_PAGE_ID, "", 0)

        for idx, col in enumerate(SYS_TABLES_COLUMNS):
            self._insert_sys_column(1, col["name"], col["type"], idx, 1 if col["name"] == "table_id" else 0)

        for idx, col in enumerate(SYS_COLUMNS_COLUMNS):
            self._insert_sys_column(2, col["name"], col["type"], idx, 1 if col["name"] == "table_id" else 0)

        for idx, col in enumerate(SYS_INDEXES_COLUMNS):
            self._insert_sys_column(3, col["name"], col["type"], idx, 0)

        self.buffer_pool.flush_all()

    # ---------- 内部页面记录读写 ----------

    def _read_all_records_from_page(self, page_id: int, columns: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        page = self.buffer_pool.get_page(page_id)
        if not page:
            return []
        count = page.get_int(0)
        recs = []
        curr = 8
        for _ in range(count):
            rec, curr = deserialize_sys_record(page.data, columns, curr)
            recs.append(rec)
        return recs

    def _append_record_to_page(self, page_id: int, record: Dict[str, Any], columns: List[Dict[str, str]]):
        page = self.buffer_pool.get_page(page_id)
        count = page.get_int(0)
        rec_bytes = serialize_sys_record(record, columns)

        # 找到当前末尾偏移量
        curr = 8
        for _ in range(count):
            _, curr = deserialize_sys_record(page.data, columns, curr)

        page.write_data(curr, rec_bytes)
        page.set_int(0, count + 1)
        self.buffer_pool.flush_page(page_id)

    def _rewrite_records_in_page(self, page_id: int, records: List[Dict[str, Any]], columns: List[Dict[str, str]]):
        page = self.buffer_pool.get_page(page_id)
        page.set_int(0, len(records))
        curr = 8
        for rec in records:
            rec_bytes = serialize_sys_record(rec, columns)
            page.write_data(curr, rec_bytes)
            curr += len(rec_bytes)
        # 清空剩余字节
        if curr < 4096:
            page.write_data(curr, b"\x00" * (4096 - curr))
        self.buffer_pool.flush_page(page_id)

    def _insert_sys_table(self, tid: int, tname: str, root_page: int, pk: str, row_count: int):
        rec = {
            "table_id": tid,
            "table_name": tname,
            "root_page": root_page,
            "primary_key": pk or "",
            "row_count": row_count
        }
        self._append_record_to_page(SYS_TABLES_PAGE_ID, rec, SYS_TABLES_COLUMNS)

    def _insert_sys_column(self, tid: int, cname: str, ctype: str, order: int, is_pk: int):
        rec = {
            "table_id": tid,
            "col_name": cname,
            "col_type": ctype,
            "col_order": order,
            "is_pk": is_pk
        }
        self._append_record_to_page(SYS_COLUMNS_PAGE_ID, rec, SYS_COLUMNS_COLUMNS)

    # ---------- 对外公共元数据接口 ----------

    def load_all_tables_meta(self) -> Dict[str, Dict[str, Any]]:
        """从 sys_tables 和 sys_columns 反序列化加载全部用户表元数据"""
        tbl_records = self._read_all_records_from_page(SYS_TABLES_PAGE_ID, SYS_TABLES_COLUMNS)
        col_records = self._read_all_records_from_page(SYS_COLUMNS_PAGE_ID, SYS_COLUMNS_COLUMNS)

        tables: Dict[str, Dict[str, Any]] = {}
        # 聚合列定义: {table_id: [col_rec, ...]}
        cols_by_tid: Dict[int, List[Dict[str, Any]]] = {}
        for c in col_records:
            cols_by_tid.setdefault(c["table_id"], []).append(c)

        for t in tbl_records:
            tname = t["table_name"]
            tid = t["table_id"]
            if tname.startswith("sys_"):
                continue  # 忽略内置系统表

            cols = cols_by_tid.get(tid, [])
            cols.sort(key=lambda x: x["col_order"])

            tables[tname] = {
                "table_id": tid,
                "root_page": t["root_page"],
                "primary_key": t["primary_key"] or None,
                "row_count": t["row_count"],
                "columns": [{"name": c["col_name"], "type": c["col_type"]} for c in cols],
                "constraints": []
            }
            if t["primary_key"]:
                tables[tname]["constraints"].append(["PRIMARY_KEY", t["primary_key"], "", ""])

        return tables

    def create_table(self, table_name: str, columns: List[Dict[str, str]], primary_key: Optional[str], root_page: int) -> int:
        """向系统表中持久化新增一张表"""
        sb = self.buffer_pool.get_page(SUPERBLOCK_PAGE_ID)
        next_tid = sb.get_int(20)
        sb.set_int(20, next_tid + 1)
        self.buffer_pool.flush_page(SUPERBLOCK_PAGE_ID)

        self._insert_sys_table(next_tid, table_name, root_page, primary_key or "", 0)

        for idx, col in enumerate(columns):
            is_pk = 1 if primary_key and col["name"] == primary_key else 0
            self._insert_sys_column(next_tid, col["name"], col["type"], idx, is_pk)

        return next_tid

    def drop_table(self, table_name: str):
        """从系统表中移除表及其所有列记录"""
        tbl_recs = self._read_all_records_from_page(SYS_TABLES_PAGE_ID, SYS_TABLES_COLUMNS)
        target_tid = None
        remaining_tbls = []
        for t in tbl_recs:
            if t["table_name"] == table_name:
                target_tid = t["table_id"]
            else:
                remaining_tbls.append(t)

        if target_tid is None:
            return

        self._rewrite_records_in_page(SYS_TABLES_PAGE_ID, remaining_tbls, SYS_TABLES_COLUMNS)

        col_recs = self._read_all_records_from_page(SYS_COLUMNS_PAGE_ID, SYS_COLUMNS_COLUMNS)
        remaining_cols = [c for c in col_recs if c["table_id"] != target_tid]
        self._rewrite_records_in_page(SYS_COLUMNS_PAGE_ID, remaining_cols, SYS_COLUMNS_COLUMNS)

    def update_row_count(self, table_name: str, row_count: int):
        """更新系统表中的行数统计"""
        tbl_recs = self._read_all_records_from_page(SYS_TABLES_PAGE_ID, SYS_TABLES_COLUMNS)
        for t in tbl_recs:
            if t["table_name"] == table_name:
                t["row_count"] = max(0, int(row_count))
        self._rewrite_records_in_page(SYS_TABLES_PAGE_ID, tbl_recs, SYS_TABLES_COLUMNS)

    def add_index(self, index_name: str, table_name: str, col_name: str, root_page: int, is_unique: int = 0):
        """向 sys_indexes 系统表登记新索引"""
        rec = {
            "index_name": index_name,
            "table_name": table_name,
            "col_name": col_name,
            "root_page": root_page,
            "is_unique": is_unique
        }
        self._append_record_to_page(SYS_INDEXES_PAGE_ID, rec, SYS_INDEXES_COLUMNS)

    def get_index_for_column(self, table_name: str, col_name: str) -> Optional[Dict[str, Any]]:
        """查询指定表的指定列是否建立了索引"""
        idx_recs = self._read_all_records_from_page(SYS_INDEXES_PAGE_ID, SYS_INDEXES_COLUMNS)
        for r in idx_recs:
            if r["table_name"] == table_name and r["col_name"] == col_name:
                return r
        return None

    def list_indexes(self, table_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出全部或某张表的全部索引"""
        idx_recs = self._read_all_records_from_page(SYS_INDEXES_PAGE_ID, SYS_INDEXES_COLUMNS)
        if table_name:
            return [r for r in idx_recs if r["table_name"] == table_name]
        return idx_recs
