# engine/executor.py
from typing import List, Dict, Any, Optional, Tuple
import datetime
import re

from storage.file_manager import FileManager
from sql_compiler.planner import ExecutionPlan
from sql_compiler.catalog import Catalog
from engine.storage_engine import StorageEngine

# ---------------- 公用：条件求值 ----------------
def _split_top_level(expr: str, delimiter: str) -> List[str]:
    expr = expr.strip()
    items: List[str] = []
    buf: List[str] = []
    depth = 0
    in_str = False
    delim_len = len(delimiter)
    is_and = (delimiter.upper() == "AND")
    between_depth = 0
    i = 0
    n = len(expr)

    while i < n:
        ch = expr[i]
        if in_str:
            buf.append(ch)
            if ch == "'":
                in_str = False
            i += 1
            continue

        if ch == "'":
            in_str = True
            buf.append(ch)
            i += 1
            continue

        if ch == "(":
            depth += 1
            buf.append(ch)
            i += 1
            continue
        if ch == ")":
            depth -= 1
            buf.append(ch)
            i += 1
            continue

        if depth == 0:
            if expr[i:i+7].upper() == "BETWEEN" and (i == 0 or not expr[i-1].isalnum()) and (i+7 == n or not expr[i+7].isalnum()):
                between_depth += 1

            if expr[i:i+delim_len].upper() == delimiter.upper() and (i == 0 or not expr[i-1].isalnum()) and (i+delim_len == n or not expr[i+delim_len].isalnum()):
                if is_and and between_depth > 0:
                    between_depth -= 1
                else:
                    items.append("".join(buf).strip())
                    buf = []
                    i += delim_len
                    continue

        buf.append(ch)
        i += 1

    if buf:
        items.append("".join(buf).strip())
    return [x for x in items if x]

def _resolve_col_from_row_fast(row: Dict[str, Any], col_name: str) -> Any:
    col_name = col_name.strip("`\" ")
    if col_name in row:
        return row[col_name]
    if "." in col_name:
        _, base = col_name.split(".", 1)
        if base in row:
            return row[base]
    candidates = [v for k, v in row.items() if k.endswith("." + col_name)]
    if len(candidates) == 1:
        return candidates[0]
    return None

def _eval_single_predicate(left_val: Any, op: str, right_str: str, row: Dict[str, Any] = None) -> bool:
    op_upper = op.upper().strip()
    if op_upper == "IS":
        return left_val is None
    elif op_upper in ("IS NOT", "IS_NOT"):
        return left_val is not None

    if left_val is None:
        return False

    if op_upper in ("LIKE", "NOT LIKE"):
        pattern = right_str.strip()
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
        matched = bool(re.match(regex_pat, str(left_val), re.IGNORECASE | re.DOTALL))
        return matched if op_upper == "LIKE" else not matched

    if op_upper in ("IN", "NOT IN"):
        s = right_str.strip().strip("()")
        parts = [p.strip().strip("'\"") for p in s.split(",")]
        match = False
        for p in parts:
            try:
                if float(left_val) == float(p):
                    match = True
                    break
            except Exception:
                if str(left_val) == str(p):
                    match = True
                    break
        return match if op_upper == "IN" else not match

    if op_upper in ("BETWEEN", "NOT BETWEEN"):
        parts = re.split(r"\s+AND\s+", right_str.strip(), flags=re.I)
        if len(parts) == 2:
            low_s, high_s = parts[0].strip().strip("'\""), parts[1].strip().strip("'\"")
            try:
                cv = float(left_val)
                lv = float(low_s)
                hv = float(high_s)
                in_range = (lv <= cv <= hv)
            except Exception:
                in_range = (str(low_s) <= str(left_val) <= str(high_s))
            return in_range if op_upper == "BETWEEN" else not in_range
        return False

    # 标准比较
    rv_raw = right_str.strip().strip("'\"")
    if rv_raw.upper() in ("TRUE", "FALSE"):
        rv = (rv_raw.upper() == "TRUE")
    elif row and rv_raw in row:
        rv = row[rv_raw]
    else:
        try:
            if "." in rv_raw: rv = float(rv_raw)
            else: rv = int(rv_raw)
        except Exception:
            rv = rv_raw

    lv = left_val
    if isinstance(lv, bool) or isinstance(rv, bool):
        lv = bool(lv)
        rv = bool(rv)
    else:
        try:
            if isinstance(lv, (int, float)) and isinstance(rv, (int, float)):
                pass
            else:
                lv = float(lv)
                rv = float(rv)
        except Exception:
            lv = str(lv)
            rv = str(rv)

    if op == "=": return lv == rv
    elif op == ">": return lv > rv
    elif op == "<": return lv < rv
    elif op == ">=": return lv >= rv
    elif op == "<=": return lv <= rv
    elif op in ("!=", "<>"): return lv != rv
    return False

def _strip_outer_parens_safe(s: str) -> str:
    s = s.strip()
    while s.startswith("(") and s.endswith(")"):
        depth = 0
        in_str = False
        all_enclosed = True
        for i, ch in enumerate(s):
            if in_str:
                if ch == "'": in_str = False
                continue
            if ch == "'":
                in_str = True
                continue
            if ch == "(": depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and i < len(s) - 1:
                    all_enclosed = False
                    break
        if all_enclosed and depth == 0:
            s = s[1:-1].strip()
        else:
            break
    return s

def _evaluate_string_condition(row: Dict[str, Any], cond_str: str) -> bool:
    if not cond_str or not str(cond_str).strip():
        return True

    cond_str = _strip_outer_parens_safe(cond_str)

    or_parts = _split_top_level(cond_str, "OR")
    if len(or_parts) > 1:
        return any(_evaluate_string_condition(row, p) for p in or_parts)

    and_parts = _split_top_level(cond_str, "AND")
    if len(and_parts) > 1:
        return all(_evaluate_string_condition(row, p) for p in and_parts)

    part = cond_str.strip()
    if not part:
        return True

    has_not = False
    if part.upper().startswith("NOT "):
        has_not = True
        part = part[4:].strip()

    part = _strip_outer_parens_safe(part)
    if not part:
        return True

    sub_or = _split_top_level(part, "OR")
    if len(sub_or) > 1:
        res = any(_evaluate_string_condition(row, p) for p in sub_or)
        return not res if has_not else res

    sub_and = _split_top_level(part, "AND")
    if len(sub_and) > 1:
        res = all(_evaluate_string_condition(row, p) for p in sub_and)
        return not res if has_not else res

    m = re.match(r"^(.*?)\s+(IS\s+NOT|IS|NOT\s+LIKE|LIKE|NOT\s+IN|IN|NOT\s+BETWEEN|BETWEEN|<=|>=|!=|<>|=|<|>)\s+(.*)$", part, re.I | re.DOTALL)
    if not m:
        m_is = re.match(r"^(.*?)\s+(IS\s+NOT\s+NULL|IS\s+NULL)$", part, re.I)
        if m_is:
            col_name = m_is.group(1).strip()
            op = "IS NOT" if "NOT" in m_is.group(2).upper() else "IS"
            val = _resolve_col_from_row_fast(row, col_name)
            res = (val is not None) if op == "IS NOT" else (val is None)
        else:
            res = True
    else:
        col_name = m.group(1).strip()
        op = m.group(2).strip()
        right_str = m.group(3).strip()
        val = _resolve_col_from_row_fast(row, col_name)
        if val is None:
            c_raw = col_name.strip("'\"")
            if (col_name.startswith("'") and col_name.endswith("'")) or (col_name.startswith('"') and col_name.endswith('"')):
                val = c_raw
            elif c_raw.upper() == "TRUE":
                val = True
            elif c_raw.upper() == "FALSE":
                val = False
            else:
                try:
                    val = float(c_raw) if "." in c_raw else int(c_raw)
                except Exception:
                    pass
        res = _eval_single_predicate(val, op, right_str, row)

    if has_not:
        res = not res
    return res

def _evaluate_condition(row: Dict[str, Any], condition: Any) -> bool:
    """
    统一条件求值：
      - 支持 Dict 条件（含 compound, IS, LIKE, IN, BETWEEN, 关系运算符）
      - 支持 SQL 字符串条件（如 'age > 18 AND name LIKE "A%"'）
    """
    if not condition:
        return True

    if isinstance(condition, str):
        return _evaluate_string_condition(row, condition)

    if isinstance(condition, dict):
        cond_type = condition.get("type")
        if cond_type == "compound":
            op = condition.get("operator", "AND").upper()
            children = condition.get("children", [])
            if op == "AND":
                return all(_evaluate_condition(row, c) for c in children)
            elif op == "OR":
                return any(_evaluate_condition(row, c) for c in children)
            elif op == "NOT":
                return not _evaluate_condition(row, children[0]) if children else True

        left = condition.get("left", {})
        op = str(condition.get("operator") or "").upper().strip()
        right = condition.get("right", {})

        col_name = left.get("value") if left.get("type") == "column" else None
        if not col_name:
            return True

        lv = _resolve_col_from_row_fast(row, col_name)

        if op == "IS":
            return lv is None
        elif op in ("IS NOT", "IS_NOT"):
            return lv is not None

        if lv is None:
            return False

        if op in ("LIKE", "NOT LIKE"):
            pat = str(right.get("value", ""))
            return _eval_single_predicate(lv, op, f"'{pat}'", row)

        if op in ("IN", "NOT IN"):
            vals = right.get("value", [])
            s = ", ".join(map(str, vals)) if isinstance(vals, (list, tuple, set)) else str(vals)
            return _eval_single_predicate(lv, op, f"({s})", row)

        if op in ("BETWEEN", "NOT BETWEEN"):
            low = right.get("low", "")
            high = right.get("high", "")
            return _eval_single_predicate(lv, op, f"{low} AND {high}", row)

        # 简单操作符
        rv = right.get("value") if isinstance(right, dict) else right
        return _eval_single_predicate(lv, op, str(rv), row)

    return True

# ---------------- 内部：类型工具 ----------------
_TYPE_NORM_MAP = {
    "INTEGER": "INT",
    "BOOLEAN": "BOOL",
    "REAL": "FLOAT",
    "NUMERIC": "DECIMAL",
    "BYTES": "BLOB",
}
_TYPE_WITH_PARAM_RE = re.compile(r"^([A-Za-z_]+)\s*(?:\(\s*(\d+)(?:\s*,\s*(\d+))?\s*\))?$", re.I)

def _parse_type(typ_str: str) -> Tuple[str, Optional[int]]:
    t = (typ_str or "").strip().upper()
    m = _TYPE_WITH_PARAM_RE.match(t)
    if m:
        base = m.group(1).upper()
        base = _TYPE_NORM_MAP.get(base, base)
        length = int(m.group(2)) if m.group(2) else None
        return base, length
    base = _TYPE_NORM_MAP.get(t, t)
    return base, None

def _coerce_runtime_value(base: str, length: Optional[int], value: Any, col_name: str) -> Any:
    """
    运行时将值转换为与列类型匹配的 Python 值，并做约束检查。
    支持所有工业级数据类型及 NULL (None)。
    """
    if value is None:
        return None
    if isinstance(value, str) and value.strip().upper() == "NULL":
        return None

    if base in ("INT", "BIGINT", "SMALLINT", "TINYINT"):
        try:
            if isinstance(value, bool):
                raise ValueError("bool is not int")
            return int(value)
        except Exception:
            raise Exception(f"Type error: column '{col_name}' expects {base}, got {repr(value)}")

    if base in ("FLOAT", "DOUBLE", "DECIMAL"):
        try:
            if isinstance(value, bool):
                raise ValueError("bool is not float")
            return float(value)
        except Exception:
            raise Exception(f"Type error: column '{col_name}' expects {base}, got {repr(value)}")

    if base == "BOOL":
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            if value in (0, 1):
                return bool(int(value))
        if isinstance(value, str):
            s = value.strip().lower()
            if s in ("true", "t", "1"):  return True
            if s in ("false", "f", "0"): return False
        raise Exception(f"Type error: column '{col_name}' expects BOOL, got {repr(value)}")

    if base in ("VARCHAR", "CHAR", "TEXT"):
        if not isinstance(value, str):
            value = str(value)
        if length is not None and len(value) > length:
            raise Exception(f"Value too long: column '{col_name}' is {base}({length}), got length {len(value)}")
        return value

    if base in ("DATE", "DATETIME", "TIMESTAMP", "TIME"):
        return str(value)

    if base == "BLOB":
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)
        return str(value).encode('utf-8')

    return str(value)

def _column_types_map(table_info: Dict[str, Any]) -> Dict[str, Tuple[str, Optional[int]]]:
    return {c["name"]: _parse_type(c["type"]) for c in table_info.get("columns", [])}

# ---------------- 执行器 ----------------
class Executor:
    def __init__(self, file_manager: FileManager, catalog: Catalog):
        self.storage_engine = StorageEngine(file_manager)
        self.file_manager = file_manager
        self.catalog = catalog

    def execute(self, plan: ExecutionPlan) -> Any:
        if plan.plan_type == "Explain":
            inner = plan.details.get("inner_plan")
            return inner.explain() if isinstance(inner, ExecutionPlan) else "Explain: <empty>"
        if plan.plan_type == "ShowTables":
            return self.execute_show_tables(plan)
        if plan.plan_type == "DescribeTable":
            return self.execute_describe_table(plan)
        if plan.plan_type == "CreateTable":
            return self.execute_create_table(plan)
        if plan.plan_type == "DropTable":
            return self.execute_drop_table(plan)
        if plan.plan_type == "TruncateTable":
            return self.execute_truncate_table(plan)
        if plan.plan_type == "AlterTable":
            return self.execute_alter_table(plan)
        if plan.plan_type == "CreateIndex":
            return self.execute_create_index(plan)
        if plan.plan_type == "DropIndex":
            return self.execute_drop_index(plan)
        if plan.plan_type == "Insert":
            return self.execute_insert(plan)
        if plan.plan_type == "Select":
            return self.execute_select(plan)
        if plan.plan_type == "Delete":
            return self.execute_delete(plan)
        if plan.plan_type == "Update":
            return self.execute_update(plan)
        raise Exception(f"Unsupported execution plan: {plan.plan_type}")

    # ---------- DDL/Admin ----------
    def execute_show_tables(self, plan: ExecutionPlan) -> List[Dict[str, Any]]:
        tables = sorted(self.catalog.list_tables())
        return [{"table_name": t, "Tables_in_database": t} for t in tables]

    def execute_describe_table(self, plan: ExecutionPlan) -> List[Dict[str, Any]]:
        table_name = plan.details["table_name"]
        info = self.catalog.get_table_info(table_name)
        if not info:
            raise Exception(f"Table '{table_name}' does not exist")
        pk = info.get("primary_key")
        rows = []
        for c in info.get("columns", []):
            is_pk = (c["name"] == pk)
            rows.append({
                "column_name": c["name"],
                "Field": c["name"],
                "type": c["type"],
                "Type": c["type"],
                "Null": "NO" if is_pk else "YES",
                "Key": "PRI" if is_pk else "",
                "Default": None,
                "Extra": ""
            })
        return rows

    def execute_drop_table(self, plan: ExecutionPlan) -> str:
        table_name = plan.details["table_name"]
        if_exists = plan.details.get("if_exists", False)
        if not self.catalog.table_exists(table_name):
            if if_exists:
                return f"Table '{table_name}' does not exist (IF EXISTS skipped)"
            raise Exception(f"Table '{table_name}' does not exist")
        self.file_manager.drop_table_file(table_name)
        self.catalog.drop_table(table_name)
        self.file_manager.flush_all()
        return f"Table '{table_name}' dropped successfully"

    def execute_truncate_table(self, plan: ExecutionPlan) -> str:
        table_name = plan.details["table_name"]
        if not self.catalog.table_exists(table_name):
            raise Exception(f"Table '{table_name}' does not exist")
        self.file_manager.delete_records(table_name, condition=None)
        self.catalog.update_row_count(table_name, 0)
        self.file_manager.flush_all()
        return f"Table '{table_name}' truncated successfully"

    def execute_alter_table(self, plan: ExecutionPlan) -> str:
        table_name = plan.details["table_name"]
        action = (plan.details["action"] or "").upper()
        col_name = plan.details["column_name"]
        col_type = plan.details.get("column_type")
        table_info = self.catalog.get_table_info(table_name)
        if not table_info:
            raise Exception(f"Table '{table_name}' does not exist")

        if action in ("ADD", "ADD_COLUMN"):
            records = self.file_manager.read_records(table_name)
            cols = list(table_info["columns"])
            cols.append({"name": col_name, "type": col_type.upper()})
            pk = table_info.get("primary_key")
            self.file_manager.drop_table_file(table_name)
            self.file_manager.create_table_file(table_name, cols, primary_key=pk)
            self.catalog.add_column(table_name, col_name, col_type)
            for r in records:
                r[col_name] = None
                self.file_manager.insert_record(table_name, r)
            self.file_manager.flush_all()
            return f"Column '{col_name}' added to table '{table_name}' successfully"
        elif action in ("DROP", "DROP_COLUMN"):
            records = self.file_manager.read_records(table_name)
            cols = [c for c in table_info["columns"] if c["name"] != col_name]
            pk = table_info.get("primary_key")
            if pk == col_name:
                pk = None
            self.file_manager.drop_table_file(table_name)
            self.file_manager.create_table_file(table_name, cols, primary_key=pk)
            self.catalog.drop_column(table_name, col_name)
            for r in records:
                r.pop(col_name, None)
                self.file_manager.insert_record(table_name, r)
            self.file_manager.flush_all()
            return f"Column '{col_name}' dropped from table '{table_name}' successfully"
        raise Exception(f"Unsupported ALTER TABLE action: {action}")

    def execute_create_index(self, plan: ExecutionPlan) -> str:
        table_name = plan.details["table_name"]
        col_name = plan.details["column_name"]
        index_name = plan.details["index_name"]
        unique = plan.details.get("unique", False)
        self.file_manager.create_index(table_name, col_name)
        self.file_manager.rebuild_indexes(table_name)
        self.catalog.add_index_meta(index_name, table_name, col_name, unique=unique)
        return f"Index '{index_name}' created on '{table_name}({col_name})' successfully"

    def execute_drop_index(self, plan: ExecutionPlan) -> str:
        index_name = plan.details["index_name"]
        if_exists = plan.details.get("if_exists", False)
        res = self.catalog.drop_index_meta(index_name)
        if not res and not if_exists:
            return f"Index '{index_name}' does not exist"
        return f"Index '{index_name}' dropped successfully"

    def execute_create_table(self, plan: ExecutionPlan) -> str:
        table_name = plan.details["table_name"]
        if plan.details.get("if_not_exists") and self.catalog.table_exists(table_name):
            return f"Table '{table_name}' already exists (IF NOT EXISTS skipped)"

        columns = plan.details["columns"]
        constraints = plan.details.get("constraints", [])
        primary_key = plan.details.get("primary_key")

        # 创建物理文件
        self.file_manager.create_table_file(table_name, columns, primary_key=primary_key)

        # 写 catalog（兼容不同函数签名）
        try:
            self.catalog.create_table(table_name, columns, constraints, primary_key)
        except TypeError:
            if hasattr(self.catalog, "create_table"):
                self.catalog.create_table(table_name, columns, constraints)
            else:
                self.catalog.create_table(table_name, columns)
                if constraints:
                    table_info = self.catalog.get_table_info(table_name)
                    table_info["constraints"] = constraints
                    self.catalog._save_catalog()
            if primary_key and hasattr(self.catalog, "set_primary_key"):
                try:
                    self.catalog.set_primary_key(table_name, primary_key)
                except Exception:
                    pass

        return f"Table '{table_name}' created successfully"

    def _normalize_values_rows(self, values) -> List[List[Tuple[str, Any]]]:
        """
        兼容 Planner 的两种形态：
          - 旧：values = [("int",1),("string","Alice")]   -> 单行
          - 新：values = [[("int",1),("string","Alice")], [("int",2),("string","Bob")]] -> 多行
        统一返回二维数组：List[Row]；Row = List[(type_tag, value)]
        """
        if not values:
            return []
        if values and values and isinstance(values[0], (list, tuple)) and len(values) > 0:
            # 判断是否已经是二维
            first = values[0]
            if first and isinstance(first, (list, tuple)) and first and isinstance(first[0], (list, tuple)):
                return values  # 已是二维
        # 否则按单行包一层
        return [values]

    def execute_insert(self, plan: ExecutionPlan) -> str:
        table_name = plan.details["table_name"]
        column_names = plan.details["column_names"] or []
        values = plan.details["values"]

        table_info = self.catalog.get_table_info(table_name)
        if not table_info:
            raise Exception(f"Table '{table_name}' does not exist")

        if not column_names:
            column_names = [col["name"] for col in table_info["columns"]]

        # 列类型映射 & 主键
        name2type = _column_types_map(table_info)
        pk_col = None
        if hasattr(self.catalog, "get_primary_key"):
            pk_col = self.catalog.get_primary_key(table_name)
        if not pk_col:
            pk_col = (table_info.get("primary_key") or None)

        # 预加载现有主键集合用于快速查重
        existing_pk_values = set()
        if pk_col:
            try:
                for r in self.file_manager.read_records(table_name):
                    if pk_col in r:
                        existing_pk_values.add(r[pk_col])
            except Exception:
                pass

        # 兼容多行
        rows = self._normalize_values_rows(values)
        inserted = 0

        for row in rows:
            # 1) 组装记录（并做类型转换/约束检查）
            if len(row) != len(column_names):
                raise Exception(f"Column count does not match value count: {len(column_names)} vs {len(row)}")

            record: Dict[str, Any] = {}
            for (typ_tag, value), col_name in zip(row, column_names):
                base, length = name2type.get(col_name, ("VARCHAR", None))
                # 值类型标签仅作参考，最终以列类型为准做强制转换
                coerced = _coerce_runtime_value(base, length, value, col_name)
                record[col_name] = coerced

            # 2) 主键唯一性检查
            if pk_col and pk_col in record:
                pk_val = record[pk_col]
                # 内存集合 + 文件过滤双保险
                if pk_val in existing_pk_values:
                    raise Exception(f"Primary key violation: '{pk_col}'={repr(pk_val)} already exists in '{table_name}'")
                # 再读一次磁盘确认（优先走 B+ 树索引）
                dup = None
                if hasattr(self.file_manager, "get_bplus_tree") and self.file_manager.get_bplus_tree(table_name, pk_col):
                    dup = self.file_manager.read_records_via_index(table_name, pk_col, pk_val, op="=")
                else:
                    cond = {
                        "left":  {"type": "column", "value": pk_col},
                        "operator": "=",
                        "right": {"type": "constant", "value_type": "string", "value": str(pk_val)}
                    }
                    dup = self.file_manager.read_records(table_name, cond)
                if dup:
                    raise Exception(f"Primary key violation: '{pk_col}'={repr(pk_val)} already exists in '{table_name}'")
                existing_pk_values.add(pk_val)

            # 3) 外键检查（沿用并增强原逻辑）
            for col_name, value in record.items():
                for constraint in table_info.get("constraints", []):
                    if constraint and constraint[0] == "FOREIGN_KEY" and constraint[1] == col_name:
                        _, _, ref_table, ref_col = constraint
                        if not self._check_reference_exists(ref_table, ref_col, value):
                            # —— 智能提示：列出现有候选值 & 修复示例 ——
                            try:
                                existing_rows = self.file_manager.read_records(ref_table)
                                vals = []
                                for r in existing_rows:
                                    if ref_col in r:
                                        vals.append(r[ref_col])
                                uniq_vals = sorted(set(vals))[:10]
                                candidates = ", ".join(map(lambda x: repr(x), uniq_vals)) if uniq_vals else "(无现有记录)"
                            except Exception:
                                candidates = "(无法读取引用表候选值)"

                            full_cols = column_names or [c["name"] for c in table_info["columns"]]
                            full_vals = [repr(record[c]) for c in full_cols]

                            # 用现有候选里第一个给出“改用现有键”的示例（若没有候选就保留原值）
                            fallback = repr(uniq_vals[0]) if 'uniq_vals' in locals() and uniq_vals else repr(value)
                            patched_vals = [
                                (fallback if c == col_name else v)
                                for c, v in zip(full_cols, full_vals)
                            ]

                            msg = (
                                f"智能提示：外键约束失败 —— {table_name}.{col_name}={repr(value)} "
                                f"在 {ref_table}({ref_col}) 中不存在。\n"
                                f"可选修复：\n"
                                f"  方案 A：先向父表插入该键值，再插入当前记录：\n"
                                f"    INSERT INTO {ref_table}({ref_col}/*, 其他列 */) VALUES ({repr(value)}/*, ... */);\n"
                                f"    INSERT INTO {table_name}({', '.join(full_cols)}) VALUES ({', '.join(full_vals)});\n"
                                f"  方案 B：改用父表中已存在的键（候选前若干：{candidates}）：\n"
                                f"    INSERT INTO {table_name}({', '.join(full_cols)}) VALUES ({', '.join(patched_vals)});"
                            )
                            raise Exception(msg)

            # 4) 落盘
            ok = self.file_manager.insert_record(table_name, record)
            if not ok:
                raise Exception("Failed to insert record")
            inserted += 1

        # 行数维护
        self.catalog.update_row_count(table_name, (self.catalog.get_table_info(table_name)["row_count"] + inserted))
        self.file_manager.flush_all()
        return f"{inserted} row(s) inserted into '{table_name}'"

    def execute_delete(self, plan: ExecutionPlan) -> str:
        table_name = plan.details["table_name"]
        condition = plan.details.get("condition")
        raw_condition = plan.details.get("raw_condition")
        table_info = self.catalog.get_table_info(table_name)
        if not table_info:
            raise Exception(f"Table '{table_name}' does not exist")
        cond = condition if condition is not None else raw_condition
        deleted = self.file_manager.delete_records(table_name, cond)
        self.catalog.update_row_count(table_name, max(0, table_info["row_count"] - deleted))
        return f"{deleted} row(s) deleted from '{table_name}'"

    def execute_update(self, plan: ExecutionPlan) -> str:
        table_name = plan.details["table_name"]
        set_clause = plan.details["set_clause"]
        condition = plan.details.get("condition")
        raw_condition = plan.details.get("raw_condition")

        table_info = self.catalog.get_table_info(table_name)
        if not table_info:
            raise Exception(f"Table '{table_name}' does not exist")

        typed_set_clause: List[Tuple[str, Any]] = []
        name2type_full = _column_types_map(table_info)

        for col_name, value_dict in set_clause:
            if col_name not in name2type_full:
                raise Exception(f"Column '{col_name}' does not exist in table '{table_name}'")
            base, length = name2type_full[col_name]
            val = value_dict["value"]
            coerced = _coerce_runtime_value(base, length, val, col_name)
            typed_set_clause.append((col_name, coerced))

        typed_condition = condition
        if condition and isinstance(condition, dict) and condition.get("left") and condition.get("right"):
            left_col = condition["left"].get("value")
            col_type = name2type_full.get(left_col, ("VARCHAR", None))
            try:
                base, length = col_type
                raw = condition["right"].get("value")
                typed_condition = dict(condition)
                typed_condition["right"] = dict(condition["right"])
                typed_condition["right"]["value"] = _coerce_runtime_value(base, length, raw, left_col)
            except Exception:
                pass

        cond = typed_condition if typed_condition is not None else raw_condition
        updated = self.file_manager.update_records(table_name, typed_set_clause, cond)

        if updated > 0 and condition and isinstance(condition, dict) and condition.get("operator") == "=":
            where_col = condition["left"]["value"]
            old_value = condition["right"]["value"]
            for set_col, new_value_dict in set_clause:
                if set_col == where_col:
                    refs = self.catalog.find_referencing_tables(table_name, set_col)
                    for ref_table, ref_col in refs:
                        cascade_plan = ExecutionPlan("Update", {
                            "table_name": ref_table,
                            "set_clause": [(ref_col, new_value_dict)],
                            "condition": {
                                "left": {"type": "column", "value": ref_col},
                                "operator": "=",
                                "right": {"type": "constant", "value_type": "string", "value": old_value},
                            }
                        })
                        self.execute_update(cascade_plan)

        return f"Updated {updated} row(s)"

    # ---------- SELECT ----------
    def execute_select(self, plan: ExecutionPlan) -> List[Dict[str, Any]]:
        ts_plan = plan.details["table_source"]
        columns: List[str] = plan.details.get("columns") or []
        aggregates: List[Dict[str, Any]] = plan.details.get("aggregates") or []
        group_by: Optional[str] = plan.details.get("group_by")
        order_by: Optional[str] = plan.details.get("order_by")
        order_dir: Optional[str] = plan.details.get("order_direction")

        # 1) 执行表源（包含谓词下推）
        raw = self._execute_table_source(ts_plan)

        # 2) 残余 WHERE 过滤（非常重要）
        residual = plan.details.get("condition")
        if residual:
            raw = [r for r in raw if _evaluate_condition(r, residual)]

        # 3) 聚合或投影
        if aggregates:
            rows = self._execute_aggregates(raw, aggregates, group_by, order_by, order_dir)
        else:
            rows = [self._project_row(row, columns) for row in raw]
            if order_by:
                rows = self._order_rows(rows, order_by, order_dir)

        # 4) HAVING 过滤
        having = plan.details.get("having")
        if having:
            rows = [r for r in rows if _evaluate_condition(r, having)]

        # 5) DISTINCT 去重
        if plan.details.get("distinct"):
            seen = set()
            deduped = []
            for r in rows:
                key = tuple(sorted((k, str(v)) for k, v in r.items()))
                if key not in seen:
                    seen.add(key)
                    deduped.append(r)
            rows = deduped

        # 6) LIMIT / OFFSET 分页切片
        offset = plan.details.get("offset") or 0
        limit = plan.details.get("limit")
        if offset > 0 or limit is not None:
            start = offset
            end = (offset + limit) if limit is not None else None
            rows = rows[start:end]

        return rows

    # ---------- 内部：GROUP BY 执行 ----------
    def _execute_group_by(self, rows: List[Dict[str, Any]], plan: ExecutionPlan) -> List[Dict[str, Any]]:
        """执行 GROUP BY 操作，必须与聚合函数一起使用"""
        group_by_col = plan.details.get("group_by")
        aggregates: List[Dict[str, Any]] = plan.details.get("aggregates") or []

        if not aggregates:
            raise Exception("[执行错误] GROUP BY 必须与聚合函数 (COUNT/SUM/AVG) 一起使用")

        # 规范化聚合项
        aggs = [{
            "func": a.get("func").upper(),
            "arg": a.get("arg"),
            "alias": a.get("alias")
        } for a in aggregates]

        # 创建分组
        groups: Dict[Any, List[Dict[str, Any]]] = {}
        for row in rows:
            key = self._resolve_col_from_row(row, group_by_col)
            groups.setdefault(key, []).append(row)

        # 为每个分组计算聚合结果
        result: List[Dict[str, Any]] = []
        for gkey, bucket in groups.items():
            one_row = {}
            # 添加分组列
            one_row[group_by_col] = gkey
            # 计算每个聚合函数
            for a in aggs:
                val = self._agg_bucket(bucket, a["func"], a["arg"])
                out_key = a["alias"] or f"{a['func']}({a['arg']})"
                one_row[out_key] = val
            result.append(one_row)

        return result

    # ---------- 内部：ORDER BY 执行 ----------
    def _execute_order_by(self, rows: List[Dict[str, Any]], plan: ExecutionPlan) -> List[Dict[str, Any]]:
        """执行 ORDER BY 操作"""
        order_by_col = plan.details.get("order_by")
        order_dir = plan.details.get("order_direction", "ASC") # 默认升序

        return self._order_rows(rows, order_by_col, order_dir)

    def _try_index_scan(self, table: str, cond: Optional[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        """尝试利用 B+ 树索引执行 IndexScan 优化"""
        if not cond or not hasattr(self.file_manager, "get_bplus_tree"):
            return None
        op = cond.get("operator")
        if op not in ("=", ">", "<", ">=", "<="):
            return None

        left = cond.get("left", {})
        right = cond.get("right", {})

        col_name = None
        val_expr = None
        actual_op = op

        if left.get("type") == "column" and right.get("type") == "constant":
            col_name = left.get("value")
            val_expr = right
            actual_op = op
        elif right.get("type") == "column" and left.get("type") == "constant":
            col_name = right.get("value")
            val_expr = left
            op_inv = {"=": "=", ">": "<", "<": ">", ">=": "<=", "<=": ">="}
            actual_op = op_inv.get(op, op)
        else:
            return None

        if not col_name or not val_expr:
            return None

        if "." in col_name:
            prefix, bare_col = col_name.split(".", 1)
            if prefix != table:
                return None
            col_name = bare_col

        tree = self.file_manager.get_bplus_tree(table, col_name)
        if not tree:
            return None

        raw_val = val_expr.get("value")
        vt = (val_expr.get("value_type") or "").lower()
        if vt == "int":
            try: target_val = int(raw_val)
            except Exception: target_val = raw_val
        elif vt == "float":
            try: target_val = float(raw_val)
            except Exception: target_val = raw_val
        elif isinstance(raw_val, str) and raw_val.isdigit():
            target_val = int(raw_val)
        else:
            target_val = raw_val

        return self.file_manager.read_records_via_index(table, col_name, target_val, op=actual_op)

    # ---------- 内部：表源执行 with 谓词下推 ----------
    def _execute_table_source(self, ts_plan: Dict) -> List[Dict[str, Any]]:
        t = ts_plan["type"]
        if t == "TableScan":
            table = ts_plan["table_name"]
            alias = ts_plan.get("alias")
            cond = ts_plan.get("condition")  # 谓词下推

            base_rows = None
            if cond:
                base_rows = self._try_index_scan(table, cond)
            if base_rows is None:
                base_rows = self.file_manager.read_records(table, cond) if cond else self.file_manager.read_records(table)

            # 无论是否有别名，都生成“带前缀键”（别名或表名）+ “裸键”
            prefix = (alias or table)
            out = []
            for r in base_rows:
                nr = {}
                for k, v in r.items():
                    nr[k] = v                       # 裸列
                    nr[f"{prefix}.{k}"] = v         # 前缀列
                out.append(nr)
            return out

        if t == "Join":
            return self._execute_join(ts_plan)

        raise Exception(f"Unsupported table source type: {t}")

    def _execute_join(self, join_plan: Dict) -> List[Dict[str, Any]]:
        join_type = join_plan["join_type"]
        left_plan = join_plan["left"]
        right_plan = join_plan["right"]
        join_condition = join_plan["condition"]

        left_rows = self._execute_table_source(left_plan)
        right_rows = self._execute_table_source(right_plan)

        results: List[Dict[str, Any]] = []

        if join_type == "INNER":
            for l in left_rows:
                for r in right_rows:
                    combined = {**l, **r}
                    if _evaluate_condition(combined, join_condition):
                        results.append(combined)
            return results

        if join_type == "LEFT":
            # 尝试确定需要补全的右表列（考虑右表为空的情况）
            right_cols = set(right_rows[0].keys()) if right_rows else set()
            if not right_cols and right_plan["type"] == "TableScan":
                rt = right_plan["table_name"]
                rp = right_plan.get("alias") or rt
                meta = self.catalog.get_table_info(rt) or {"columns": []}
                right_cols = {f"{rp}.{c['name']}" for c in meta["columns"]} | {c['name'] for c in meta["columns"]}

            for l in left_rows:
                matched = False
                for r in right_rows:
                    combined = {**l, **r}
                    if _evaluate_condition(combined, join_condition):
                        results.append(combined)
                        matched = True
                if not matched:
                    combined = dict(l)
                    for c in right_cols:
                        combined.setdefault(c, None)
                    results.append(combined)
            return results

        if join_type == "CROSS":
            for l in left_rows:
                for r in right_rows:
                    combined = {**l, **r}
                    if not join_condition or _evaluate_condition(combined, join_condition):
                        results.append(combined)
            return results

        if join_type == "RIGHT":
            left_cols = set(left_rows[0].keys()) if left_rows else set()
            if not left_cols and left_plan["type"] == "TableScan":
                lt = left_plan["table_name"]
                lp = left_plan.get("alias") or lt
                meta = self.catalog.get_table_info(lt) or {"columns": []}
                left_cols = {f"{lp}.{c['name']}" for c in meta["columns"]} | {c['name'] for c in meta["columns"]}

            for r in right_rows:
                matched = False
                for l in left_rows:
                    combined = {**l, **r}
                    if _evaluate_condition(combined, join_condition):
                        results.append(combined)
                        matched = True
                if not matched:
                    combined = dict(r)
                    for c in left_cols:
                        combined.setdefault(c, None)
                    results.append(combined)
            return results

        raise Exception(f"Unsupported join type: {join_type}")

    # ---------- 内部：聚合/分组/排序/投影 ----------
    def _resolve_col_from_row(self, row: Dict[str, Any], col: str):
        if col in row:
            return row[col]
        if "." in col:
            _, base = col.split(".", 1)
            if base in row:
                return row[base]
        hits = [v for k, v in row.items() if k.endswith("." + col)]
        if len(hits) == 1:
            return hits[0]
        return None

    def _execute_aggregates(self,
                            rows: List[Dict[str, Any]],
                            aggregates: List[Dict[str, Any]],
                            group_by: Optional[str],
                            order_by: Optional[str],
                            order_dir: Optional[str]) -> List[Dict[str, Any]]:
        # 规范化聚合项：{'func','arg','alias'}
        aggs = [{
            "func": a.get("func").upper(),
            "arg": a.get("arg"),
            "alias": a.get("alias")
        } for a in aggregates]

        if group_by:
            # 分组键（单列）
            groups: Dict[Any, List[Dict[str, Any]]] = {}
            for row in rows:
                key = self._resolve_col_from_row(row, group_by)
                groups.setdefault(key, []).append(row)

            out: List[Dict[str, Any]] = []
            for gkey, bucket in groups.items():
                one = {}
                one[group_by] = gkey
                for a in aggs:
                    val = self._agg_bucket(bucket, a["func"], a["arg"])
                    out_key = a["alias"] or f"{a['func']}({a['arg']})"
                    one[out_key] = val
                out.append(one)

            if order_by:
                out = self._order_rows(out, order_by, order_dir)
            return out

        # 无分组：全表聚合 -> 单行
        res: Dict[str, Any] = {}
        for a in aggs:
            val = self._agg_bucket(rows, a["func"], a["arg"])
            out_key = a["alias"] or f"{a['func']}({a['arg']})"
            res[out_key] = val
        return [res]

    def _agg_bucket(self, bucket: List[Dict[str, Any]], func: str, arg: str) -> Any:
        if func == "COUNT" and arg == "*":
            return len(bucket)
        vals: List[Any] = []
        for row in bucket:
            v = self._resolve_col_from_row(row, arg)
            if v is None:
                continue
            if func in ("SUM", "AVG"):
                try:
                    v = float(v)
                except Exception:
                    continue
            vals.append(v)

        if func == "COUNT":
            return len(vals)
        if func == "SUM":
            return sum(vals) if vals else 0
        if func == "AVG":
            return (sum(vals) / len(vals)) if vals else 0
        if func == "MAX":
            if not vals:
                return None
            try:
                return max(float(x) if isinstance(x, (int, float, str)) and str(x).replace('.', '', 1).replace('-', '', 1).isdigit() else x for x in vals)
            except Exception:
                return max(vals)
        if func == "MIN":
            if not vals:
                return None
            try:
                return min(float(x) if isinstance(x, (int, float, str)) and str(x).replace('.', '', 1).replace('-', '', 1).isdigit() else x for x in vals)
            except Exception:
                return min(vals)
        raise Exception(f"Unsupported aggregate function: {func}")

    def _eval_scalar_func(self, row: Dict[str, Any], fn_name: str, arg: str) -> Any:
        fn = fn_name.upper()
        if fn == "NOW":
            return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        arg = arg.strip()
        val = self._resolve_col_from_row(row, arg) if arg else None
        if val is None and arg:
            if (arg.startswith("'") and arg.endswith("'")) or (arg.startswith('"') and arg.endswith('"')):
                val = arg[1:-1]
            else:
                try: val = float(arg)
                except Exception: val = arg

        if fn == "UPPER":
            return str(val).upper() if val is not None else None
        if fn == "LOWER":
            return str(val).lower() if val is not None else None
        if fn == "LENGTH":
            return len(str(val)) if val is not None else 0
        if fn == "ABS":
            try: return abs(float(val)) if val is not None else None
            except Exception: return val
        if fn == "ROUND":
            try: return float(round(float(val))) if val is not None else None
            except Exception: return val
        return val

    def _parse_select_column_item(self, item: str) -> Tuple[str, Optional[str]]:
        s = item.strip()
        m = re.match(r"^(.*?)\s+AS\s+(.+)$", s, re.I)
        if m:
            expr = m.group(1).strip()
            alias = m.group(2).strip().strip("'\"`")
            return expr, alias
        return s, None

    def _project_row(self, row: Dict[str, Any], columns: List[str]) -> Dict[str, Any]:
        if not columns or columns == ["*"]:
            return {k: v for k, v in row.items() if '.' not in k}
        out: Dict[str, Any] = {}
        for col_item in columns:
            if col_item == "*":
                out.update(row)
                continue
            expr, alias = self._parse_select_column_item(col_item)
            m_fn = re.match(r"^\s*(UPPER|LOWER|LENGTH|NOW|ABS|ROUND)\s*\(\s*(.*?)\s*\)\s*$", expr, re.I)
            if m_fn:
                val = self._eval_scalar_func(row, m_fn.group(1), m_fn.group(2))
            else:
                val = self._resolve_col_from_row(row, expr)
            out[alias or expr] = val
        return out

    def _order_rows(self, rows: List[Dict[str, Any]], key_name: str, direction: Optional[str]) -> List[Dict[str, Any]]:
        """根据指定的列名和方向对行进行排序"""
        rev = (isinstance(direction, str) and direction.upper() == "DESC")

        def _key_func(row):
            # 尝试从行中获取排序键的值
            val = self._resolve_col_from_row(row, key_name)
            # 如果值是 None，我们将其放在最后（对于升序）或最前（对于降序）
            # 通过返回一个元组 (priority, actual_value) 来实现
            if val is None:
                return (1, None) if not rev else (-1, None)
            else:
                return (0, val)

        return sorted(rows, key=_key_func, reverse=rev)

    # ---------- 其他 ----------
    def _check_reference_exists(self, table_name, column_name, value):
        table_info = self.catalog.get_table_info(table_name)
        if not table_info:
            return False
        if hasattr(self.file_manager, "get_bplus_tree") and self.file_manager.get_bplus_tree(table_name, column_name):
            records = self.file_manager.read_records_via_index(table_name, column_name, value, op="=")
            return len(records) > 0
        cond = {
            "left":  {"type": "column", "value": column_name},
            "operator": "=",
            "right": {"type": "constant", "value_type": "string", "value": str(value)}
        }
        records = self.file_manager.read_records(table_name, cond)
        return len(records) > 0
