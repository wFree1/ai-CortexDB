# SQL编译器 - 目录管理（兼容 add_table / create_table、支持外键与行数维护、主键持久化）

import json
import os
from typing import Dict, List, Any, Optional, Tuple


import logging

logger = logging.getLogger("catalog")


class Catalog:
    """
    轻量目录服务：
      - 将所有表的元信息持久化到 catalog_file（默认 data/catalog.json）
      - 结构：
        {
          "users": {
            "columns": [{"name": "id", "type": "INT"}, {"name": "name", "type": "VARCHAR(20)"}],
            "primary_key": "id",                 # 新增：可选
            "row_count": 0,
            "constraints": [
              ["FOREIGN_KEY", "class_id", "class", "id"]
            ]
          },
          ...
        }
    """
    def __init__(self, catalog_file: Optional[str] = None, data_dir: Optional[str] = None, buffer_pool: Optional[Any] = None):
        self.buffer_pool = buffer_pool
        self.sys_catalog = None

        if catalog_file:
            self.catalog_file = catalog_file
        elif data_dir:
            self.catalog_file = os.path.join(data_dir, 'catalog.json')
        else:
            self.catalog_file = os.path.join('data', 'catalog.json')

        self.tables: Dict[str, Dict[str, Any]] = {}

        if self.buffer_pool:
            from storage.sys_catalog import SysCatalogManager
            self.sys_catalog = SysCatalogManager(self.buffer_pool)
            self.tables = self.sys_catalog.load_all_tables_meta()
        else:
            self._load_catalog_from_file()

    # ---------------- 文件读写 ----------------

    def _ensure_parent_dir(self):
        parent = os.path.dirname(self.catalog_file) or "."
        os.makedirs(parent, exist_ok=True)

    def _load_catalog_from_file(self):
        """从文件加载目录；文件不存在则保持空目录。"""
        if os.path.exists(self.catalog_file):
            try:
                with open(self.catalog_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.tables = data
                    else:
                        logger.warning(f"{self.catalog_file} 内容不是字典，将使用空目录并在保存时覆盖。")
            except json.JSONDecodeError:
                logger.warning(f"{self.catalog_file} 文件损坏，将创建新的空目录")
            except Exception as e:
                logger.warning(f"加载目录时发生错误: {e}")
        else:
            logger.debug(f"目录文件 {self.catalog_file} 不存在，将创建新的空目录")

    def _save_catalog(self):
        self._ensure_parent_dir()
        with open(self.catalog_file, 'w', encoding='utf-8') as f:
            json.dump(self.tables, f, indent=2, ensure_ascii=False)

    def to_dict(self) -> Dict[str, Any]:
        """返回所有表元数据的深拷贝副本"""
        import copy
        return copy.deepcopy(self.tables)

    def get_schema_summary(self) -> str:
        """生成人类/大模型友好的数据库结构描述文本"""
        if not self.tables:
            return "数据库中当前没有任何数据表。"

        lines = ["=== 数据库结构 (Schema) ==="]
        for tbl_name, info in self.tables.items():
            pk = info.get("primary_key")
            row_cnt = info.get("row_count", 0)
            lines.append(f"\n表名: {tbl_name} (当前行数: {row_cnt})")
            lines.append("  列定义:")
            for col in info.get("columns", []):
                cname = col.get("name")
                ctype = col.get("type")
                is_pk = " [主键 PRIMARY KEY]" if cname == pk else ""
                lines.append(f"    - {cname}: {ctype}{is_pk}")

            constraints = info.get("constraints", [])
            fk_list = [c for c in constraints if isinstance(c, (list, tuple)) and len(c) >= 4 and c[0] == "FOREIGN_KEY"]
            if fk_list:
                lines.append("  外键约束:")
                for fk in fk_list:
                    lines.append(f"    - {fk[1]} -> {fk[2]}({fk[3]})")

        return "\n".join(lines)

    # ---------------- 基础查询/判断 ----------------

    def table_exists(self, table_name: str) -> bool:
        return table_name in self.tables

    def list_tables(self) -> List[str]:
        return list(self.tables.keys())

    def get_table_info(self, table_name: str) -> Optional[Dict[str, Any]]:
        """
        返回表的完整元信息字典：
          { "columns": [...], "primary_key": str|None, "row_count": int, "constraints": [...] }
        """
        return self.tables.get(table_name)

    # 便捷：列工具
    def has_column(self, table_name: str, column_name: str) -> bool:
        info = self.get_table_info(table_name) or {}
        return any(c.get("name") == column_name for c in info.get("columns", []))

    def get_column_type(self, table_name: str, column_name: str) -> Optional[str]:
        info = self.get_table_info(table_name) or {}
        for c in info.get("columns", []):
            if c.get("name") == column_name:
                return c.get("type")
        return None

    def columns_map(self, table_name: str) -> Dict[str, str]:
        """返回 {列名: 类型} 映射"""
        info = self.get_table_info(table_name) or {}
        return {c.get("name"): c.get("type") for c in info.get("columns", [])}

    # ---------------- 主键管理 ----------------

    def get_primary_key(self, table_name: str) -> Optional[str]:
        info = self.get_table_info(table_name) or {}
        return info.get("primary_key")

    def set_primary_key(self, table_name: str, column_name: Optional[str]):
        if table_name not in self.tables:
            raise Exception(f"Table '{table_name}' does not exist")
        if column_name is not None and not self.has_column(table_name, column_name):
            raise Exception(f"Column '{column_name}' does not exist in table '{table_name}'")
        self.tables[table_name]["primary_key"] = column_name
        self._save_catalog()

    # ---------------- 创建 / 兼容方法 ----------------

    def create_table(self, table_name: str,
                     columns: List[Dict[str, str]],
                     constraints: Optional[List[Tuple]] = None,
                     primary_key: Optional[str] = None):
        """
        新建表。
        :param table_name: 表名
        :param columns: 形如 [{"name":"id","type":"INT"}, {"name":"name","type":"VARCHAR(20)"}]
        :param constraints: 形如 [("FOREIGN_KEY", "col", "ref_table", "ref_col"), ...]
        :param primary_key: 可选，主键列名（单列主键）
        """
        if self.table_exists(table_name):
            raise Exception(f"Table '{table_name}' already exists")

        # 基本校验（尽量宽松，避免和前端/编译阶段重复）
        norm_cols: List[Dict[str, str]] = []
        for c in columns or []:
            if not isinstance(c, dict) or "name" not in c or "type" not in c:
                raise Exception(f"Invalid column spec: {c}")
            norm_cols.append({"name": str(c["name"]), "type": str(c["type"]).upper()})

        if primary_key is not None:
            if not any(col["name"] == primary_key for col in norm_cols):
                raise Exception(f"Primary key column '{primary_key}' is not defined in columns")

        self.tables[table_name] = {
            "columns": norm_cols,
            "primary_key": primary_key,            # 新增
            "row_count": 0,
            "constraints": list(constraints or [])
        }
        if self.sys_catalog:
            self.sys_catalog.create_table(table_name, norm_cols, primary_key, root_page=-1)
        self._save_catalog()

    # add_table 与 create_table 等价（增加 primary_key 参数）
    def add_table(self, table_name: str, columns: List[Dict[str, str]],
                  constraints: Optional[List[Tuple]] = None,
                  primary_key: Optional[str] = None):
        """
        兼容旧接口：等价于 create_table。
        某些模块（如 executor / planner 的旧版本）可能调用 add_table。
        """
        self.create_table(table_name, columns, constraints, primary_key)

    # ---------------- 删除 / 更新 ----------------

    def drop_table(self, table_name: str):
        if table_name in self.tables:
            del self.tables[table_name]
            if self.sys_catalog:
                self.sys_catalog.drop_table(table_name)
            self._save_catalog()

    def update_row_count(self, table_name: str, count: int):
        """
        更新某表记录数（执行器在插入/删除后应调用）。
        """
        if table_name not in self.tables:
            raise Exception(f"Table '{table_name}' does not exist")
        # 行数下限为 0
        new_cnt = max(0, int(count))
        self.tables[table_name]["row_count"] = new_cnt
        if self.sys_catalog:
            self.sys_catalog.update_row_count(table_name, new_cnt)
        self._save_catalog()

    # ---------------- 约束管理（包含外键） ----------------

    def add_constraint(self, table_name: str, constraint: Tuple):
        """
        添加一条约束，constraint 建议为 tuple：
          - 外键：("FOREIGN_KEY", local_col, ref_table, ref_col)
        """
        if table_name not in self.tables:
            raise Exception(f"Table '{table_name}' does not exist")
        self.tables[table_name].setdefault("constraints", []).append(tuple(constraint))
        self._save_catalog()

    def add_foreign_key(self, table_name: str, local_col: str,
                        ref_table: str, ref_col: str):
        """
        便捷方法：添加外键约束。
        """
        self.add_constraint(table_name, ("FOREIGN_KEY", local_col, ref_table, ref_col))

    def find_referencing_tables(self, target_table: str, target_column: str) -> List[Tuple[str, str]]:
        """
        查找所有外键引用了指定表和列的表。
        返回: [(引用表名, 引用列名), ...]
        """
        referencing: List[Tuple[str, str]] = []
        for tbl, meta in self.tables.items():
            for constraint in meta.get("constraints", []):
                # 兼容 list/tuple 形式
                try:
                    kind = constraint[0]
                    if (kind == "FOREIGN_KEY"
                        and len(constraint) >= 4
                        and constraint[2] == target_table
                        and constraint[3] == target_column):
                        referencing.append((tbl, constraint[1]))
                except Exception:
                    # 非法的约束元组，忽略
                    continue
        return referencing

    def add_column(self, table_name: str, col_name: str, col_type: str):
        if table_name not in self.tables:
            raise Exception(f"Table '{table_name}' does not exist")
        cols = self.tables[table_name].setdefault("columns", [])
        if any(c["name"] == col_name for c in cols):
            raise Exception(f"Column '{col_name}' already exists in table '{table_name}'")
        cols.append({"name": col_name, "type": col_type.upper()})
        self._save_catalog()

    def drop_column(self, table_name: str, col_name: str):
        if table_name not in self.tables:
            raise Exception(f"Table '{table_name}' does not exist")
        cols = self.tables[table_name].get("columns", [])
        if not any(c["name"] == col_name for c in cols):
            raise Exception(f"Column '{col_name}' does not exist in table '{table_name}'")
        self.tables[table_name]["columns"] = [c for c in cols if c["name"] != col_name]
        self._save_catalog()

    def add_index_meta(self, index_name: str, table_name: str, col_name: str, unique: bool = False):
        if table_name not in self.tables:
            raise Exception(f"Table '{table_name}' does not exist")
        idx_dict = self.tables[table_name].setdefault("indexes", {})
        idx_dict[index_name] = {"column": col_name, "unique": unique}
        self._save_catalog()

    def drop_index_meta(self, index_name: str) -> Optional[Tuple[str, str]]:
        for tbl, meta in self.tables.items():
            idx_dict = meta.get("indexes", {})
            if index_name in idx_dict:
                col = idx_dict[index_name]["column"]
                del idx_dict[index_name]
                self._save_catalog()
                return tbl, col
        return None

