# 严格 LL(1) 辅助的解析器：先用 FIRST/FOLLOW+预测表做推导可视化（教学），再用递归下降构建 AST
# 调试仿真不会消费实际 tokens

from typing import List, Dict, Set, Optional, Tuple, Any, Callable
from sql_compiler.lexer import Token
from sql_compiler.diag import caret_line, suggest_expected_vs_got, nearest


# ---------------- AST 节点 ----------------
class ASTNode:
    pass


class ExplainNode(ASTNode):
    def __init__(self, inner: ASTNode):
        self.inner = inner
    def __repr__(self):
        return f"ExplainNode({self.inner})"


class CreateTableNode(ASTNode):
    def __init__(self, table_name: str, columns: List[Tuple[str, str]],
                 constraints: Optional[List[Tuple[str, str, str, str]]] = None,
                 if_not_exists: bool = False,
                 pos: Optional[int] = None):
        self.table_name = table_name
        self.columns = columns
        self.constraints = constraints or []  # e.g. ('FOREIGN_KEY', 'dept_id', 'departments', 'dept_id') / ('PRIMARY_KEY','id','','')
        self.if_not_exists = if_not_exists
        self.pos = pos

    def __repr__(self):
        cols = ", ".join(f"{n} {t}" for n, t in self.columns)
        cons = "; ".join([f"{c[0]}({c[1]}) REF {c[2]}({c[3]})" if c[0] == "FOREIGN_KEY" else f"{c[0]}({c[1]})" for c in self.constraints]) if self.constraints else ""
        ine = "IF NOT EXISTS " if self.if_not_exists else ""
        return f"CreateTableNode({ine}{self.table_name}, [{cols}]{'; ' + cons if cons else ''})"


class InsertNode(ASTNode):
    def __init__(self, table_name: str, column_names: List[str], values: List[List[Any]], pos: Optional[int] = None):
        self.table_name = table_name
        self.column_names = column_names
        self.values = values
        self.pos = pos

    def __repr__(self):
        vals = "; ".join([f"({', '.join(map(str, row))})" for row in self.values])
        cols = f"({', '.join(self.column_names)})" if self.column_names else ""
        return f"InsertNode({self.table_name}{cols}, VALUES {vals})"


class SelectNode(ASTNode):
    def __init__(self, select_items: List[Tuple[str, Optional[str]]], from_table: str,
                 from_alias: Optional[str] = None, pos: Optional[int] = None,
                 distinct: bool = False,
                 limit: Optional[int] = None,
                 offset: Optional[int] = None,
                 having: Optional[str] = None):
        self.select_items = select_items  # [(expr_sql, alias_or_None)]
        self.from_table = from_table
        self.from_alias = from_alias
        self.distinct = distinct
        # (right_table, alias, condition_sql, join_type)
        self.joins: List[Tuple[str, Optional[str], str, str]] = []
        self.where_condition: Optional[str] = None
        self.group_by: Optional[str] = None
        self.group_by_cols: List[str] = []
        self.having: Optional[str] = having
        self.order_by: Optional[str] = None
        self.order_direction: Optional[str] = None
        self.limit: Optional[int] = limit
        self.offset: Optional[int] = offset
        self.pos = pos

    def __repr__(self):
        items = ", ".join((f"{e} AS {a}" if a else e) for e, a in self.select_items)
        d = "DISTINCT " if self.distinct else ""
        j = ""
        if self.joins:
            j = " " + " ".join([f"{jt} JOIN {t}{(' ' + a) if a else ''} ON {cond}" for t, a, cond, jt in self.joins])
        w = f" WHERE {self.where_condition}" if self.where_condition else ""
        g = f" GROUP BY {self.group_by}" if self.group_by else ""
        h = f" HAVING {self.having}" if self.having else ""
        o = f" ORDER BY {self.order_by}{(' ' + self.order_direction) if self.order_direction else ''}" if self.order_by else ""
        lim = f" LIMIT {self.limit}" if self.limit is not None else ""
        off = f" OFFSET {self.offset}" if self.offset is not None else ""
        return f"SelectNode(SELECT {d}{items} FROM {self.from_table}{(' ' + self.from_alias) if self.from_alias else ''}{j}{w}{g}{h}{o}{lim}{off})"


class DeleteNode(ASTNode):
    def __init__(self, table_name: str, pos: Optional[int] = None):
        self.table_name = table_name
        self.where_condition = None
        self.pos = pos

    def __repr__(self):
        w = f" WHERE {self.where_condition}" if self.where_condition else ""
        return f"DeleteNode(DELETE FROM {self.table_name}{w})"


class UpdateNode(ASTNode):
    def __init__(self, table_name: str, assignments: List[Tuple[str, Any]], pos: Optional[int] = None):
        self.table_name = table_name
        self.assignments = assignments
        self.where_condition = None
        self.pos = pos

    def __repr__(self):
        def fmt(v):
            if isinstance(v, str) and not (v.startswith("'") and v.endswith("'")) and "." not in v:
                return f"'{v}'"
            return v
        assigns = ", ".join([f"{c}={fmt(v)}" for c, v in self.assignments])
        w = f" WHERE {self.where_condition}" if self.where_condition else ""
        return f"UpdateNode(UPDATE {self.table_name} SET {assigns}{w})"


class DropTableNode(ASTNode):
    def __init__(self, table_name: str, if_exists: bool = False, pos: Optional[int] = None):
        self.table_name = table_name
        self.if_exists = if_exists
        self.pos = pos

    def __repr__(self):
        return f"DropTableNode({self.table_name}, if_exists={self.if_exists})"


class TruncateTableNode(ASTNode):
    def __init__(self, table_name: str, pos: Optional[int] = None):
        self.table_name = table_name
        self.pos = pos

    def __repr__(self):
        return f"TruncateTableNode({self.table_name})"


class AlterTableNode(ASTNode):
    def __init__(self, table_name: str, action: str, column_name: str, column_type: Optional[str] = None, pos: Optional[int] = None):
        self.table_name = table_name
        self.action = action.upper()  # "ADD" or "DROP"
        self.column_name = column_name
        self.column_type = column_type
        self.pos = pos

    def __repr__(self):
        return f"AlterTableNode({self.table_name}, {self.action} {self.column_name} {self.column_type})"


class CreateIndexNode(ASTNode):
    def __init__(self, index_name: str, table_name: str, column_name: str, if_not_exists: bool = False, pos: Optional[int] = None):
        self.index_name = index_name
        self.table_name = table_name
        self.column_name = column_name
        self.if_not_exists = if_not_exists
        self.pos = pos

    def __repr__(self):
        return f"CreateIndexNode({self.index_name} ON {self.table_name}({self.column_name}))"


class DropIndexNode(ASTNode):
    def __init__(self, index_name: str, table_name: Optional[str] = None, if_exists: bool = False, pos: Optional[int] = None):
        self.index_name = index_name
        self.table_name = table_name
        self.if_exists = if_exists
        self.pos = pos

    def __repr__(self):
        return f"DropIndexNode({self.index_name})"


class ShowTablesNode(ASTNode):
    def __init__(self, pos: Optional[int] = None):
        self.pos = pos

    def __repr__(self):
        return "ShowTablesNode()"


class CreateDatabaseNode(ASTNode):
    def __init__(self, db_name: str, if_not_exists: bool = False, pos: Optional[int] = None):
        self.db_name = db_name
        self.if_not_exists = if_not_exists
        self.pos = pos

    def __repr__(self):
        return f"CreateDatabaseNode({self.db_name}, if_not_exists={self.if_not_exists})"


class DropDatabaseNode(ASTNode):
    def __init__(self, db_name: str, if_exists: bool = False, pos: Optional[int] = None):
        self.db_name = db_name
        self.if_exists = if_exists
        self.pos = pos

    def __repr__(self):
        return f"DropDatabaseNode({self.db_name}, if_exists={self.if_exists})"


class UseDatabaseNode(ASTNode):
    def __init__(self, db_name: str, pos: Optional[int] = None):
        self.db_name = db_name
        self.pos = pos

    def __repr__(self):
        return f"UseDatabaseNode({self.db_name})"


class ShowDatabasesNode(ASTNode):
    def __init__(self, pos: Optional[int] = None):
        self.pos = pos

    def __repr__(self):
        return "ShowDatabasesNode()"


class DescribeTableNode(ASTNode):
    def __init__(self, table_name: str, pos: Optional[int] = None):
        self.table_name = table_name
        self.pos = pos

    def __repr__(self):
        return f"DescribeTableNode({self.table_name})"


# ---------------- token -> 文法符号 映射（用于 LL(1) 仿真） ----------------
def token_to_symbol(tok: Optional[Token]) -> str:
    """把 lexer 的 Token 映射成文法里的终结符（用于 LL1 推导仿真）"""
    if tok is None:
        return "#"
    ttype = getattr(tok, "type", "")
    tval = str(tok.value)

    if ttype == "KEYWORD":
        kw = tval.upper()
        if kw in ("AND", "OR", "NOT", "ASC", "DESC", "SELECT", "FROM", "JOIN", "ON",
                  "WHERE", "GROUP", "BY", "ORDER", "INSERT", "INTO", "VALUES",
                  "CREATE", "TABLE", "DELETE", "UPDATE", "SET",
                  "INT", "VARCHAR", "FLOAT", "BOOL",
                  "FOREIGN", "KEY", "REFERENCES", "PRIMARY",
                  "COUNT", "SUM", "AVG", "EXPLAIN"):
            return kw
        return kw
    if ttype == "IDENTIFIER":
        return "IDENTIFIER"
    if ttype == "NUMBER":
        return "NUMBER"
    if ttype == "STRING":
        return "STRING"
    if ttype == "OPERATOR":
        return "OPERATOR"
    if ttype == "DELIMITER":
        if tval in ("(", ")", ",", ";", ".", "*"):
            return tval
        if tval in ("=",):
            return "OPERATOR"
        return tval
    if isinstance(tok.value, str):
        return tok.value.upper()
    return str(tok.value)


# ---------------- FIRST / FOLLOW / 预测表 与 LL(1) 仿真 ----------------
def compute_first_sets(grammar: Dict[str, List[List[str]]], terminals: Set[str]) -> Dict[str, Set[str]]:  # noqa
    FIRST: Dict[str, Set[str]] = {nt: set() for nt in grammar}
    changed = True
    while changed:
        changed = False
        for A, prods in grammar.items():
            for prod in prods:
                if prod == ["ε"] or len(prod) == 0:
                    if "ε" not in FIRST[A]:
                        FIRST[A].add("ε"); changed = True
                    continue
                add_eps = True
                for X in prod:
                    if X in terminals:
                        if X not in FIRST[A]:
                            FIRST[A].add(X); changed = True
                        add_eps = False
                        break
                    else:
                        for s in FIRST.get(X, set()):
                            if s != "ε" and s not in FIRST[A]:
                                FIRST[A].add(s); changed = True
                        if "ε" in FIRST.get(X, set()):
                            add_eps = True
                        else:
                            add_eps = False
                        if not add_eps:
                            break
                if add_eps:
                    if "ε" not in FIRST[A]:
                        FIRST[A].add("ε"); changed = True
    return FIRST


def compute_follow_sets(grammar: Dict[str, List[List[str]]], start_symbol: str, terminals: Set[str],  # noqa
                        FIRST: Dict[str, Set[str]]) -> Dict[str, Set[str]]:
    FOLLOW: Dict[str, Set[str]] = {nt: set() for nt in grammar}
    FOLLOW[start_symbol].add("#")
    changed = True
    while changed:
        changed = False
        for A, prods in grammar.items():
            for prod in prods:
                for i, B in enumerate(prod):
                    if B not in grammar:
                        continue
                    beta = prod[i+1:]
                    if not beta:
                        before = len(FOLLOW[B])
                        FOLLOW[B].update(FOLLOW[A])
                        if len(FOLLOW[B]) != before:
                            changed = True
                    else:
                        first_beta = set()
                        contains_eps = True
                        for sym in beta:
                            if sym in terminals:
                                first_beta.add(sym); contains_eps = False; break
                            else:
                                first_beta.update(x for x in FIRST.get(sym, set()) if x != "ε")
                                if "ε" in FIRST.get(sym, set()):
                                    contains_eps = True
                                else:
                                    contains_eps = False; break
                        before = len(FOLLOW[B])
                        FOLLOW[B].update(first_beta)
                        if contains_eps:
                            FOLLOW[B].update(FOLLOW[A])
                        if len(FOLLOW[B]) != before:
                            changed = True
    return FOLLOW


def build_parse_table(grammar: Dict[str, List[List[str]]], terminals: Set[str],  # noqa
                      FIRST: Dict[str, Set[str]], FOLLOW: Dict[str, Set[str]]):
    table: Dict[Tuple[str, str], List[str]] = {}
    for A, prods in grammar.items():
        for prod in prods:
            first_prod = set()
            if prod == ["ε"] or len(prod) == 0:
                first_prod.add("ε")
            else:
                contains_eps = True
                for sym in prod:
                    if sym in terminals:
                        first_prod.add(sym); contains_eps = False; break
                    else:
                        first_prod.update(x for x in FIRST.get(sym, set()) if x != "ε")
                        if "ε" in FIRST.get(sym, set()):
                            contains_eps = True
                        else:
                            contains_eps = False; break
                if contains_eps:
                    first_prod.add("ε")
            for a in first_prod:
                if a != "ε":
                    key = (A, a)
                    table[key] = prod
            if "ε" in first_prod:
                for b in FOLLOW.get(A, set()):
                    key = (A, b)
                    table[key] = prod
    return table


def ll1_simulate(tokens: List[Token],  # noqa
                 grammar: Dict[str, List[List[str]]],
                 start_symbol: str,
                 terminals: Set[str],
                 on_expected: Optional[Callable[[List[str]], None]] = None):
    FIRST = compute_first_sets(grammar, terminals)
    FOLLOW = compute_follow_sets(grammar, start_symbol, terminals, FIRST)
    table = build_parse_table(grammar, terminals, FIRST, FOLLOW)

    input_symbols = [token_to_symbol(t) for t in tokens] + ["#"]
    stack: List[str] = ["#", start_symbol]

    print("\n[LL1 推导过程]")
    def stack_str():
        return " ".join(stack)
    def input_str():
        return " ".join(input_symbols)

    ip = 0
    while stack:
        top = stack[-1]
        cur = input_symbols[ip] if ip < len(input_symbols) else "#"
        print(f"栈: {stack_str():<70} 输入: {input_str():<70} # 处理: {top}")
        if top == "#":
            if cur == "#":
                print("[OK] 输入完整匹配，分析成功")
                return True
            else:
                print(f"[FAIL] 出错: 栈到达底 (#)，但输入尚未结束 -> {cur}")
                return False
        if top in terminals:
            if top == cur:
                stack.pop(); ip += 1; continue
            else:
                tok = tokens[ip] if ip < len(tokens) else None
                if tok:
                    print(f"[FAIL] 出错: 期望 {top}, 实际 {cur} (line={tok.line}, col={tok.column})")
                else:
                    print(f"[FAIL] 出错: 期望 {top}, 实际 EOF")
                return False
        else:
            key = (top, cur)
            prod = table.get(key)
            if prod is None:
                expected = sorted({a for (A, a) in table.keys() if A == top})
                if on_expected:
                    on_expected(list(expected))
                tok = tokens[ip] if ip < len(tokens) else None
                if tok:
                    exp_str = ", ".join(expected) if expected else "N/A"
                    print(f"[FAIL] 出错: 无法从 {top} 推导输入 {cur}")
                    print(f"[语法错误] 期望其中之一: {exp_str}, 实际 {cur} (line={tok.line}, col={tok.column})")
                else:
                    print(f"[FAIL] 出错: 无法从 {top} 推导输入 EOF")
                return False
            if on_expected:
                expected_now = sorted({a for (A, a) in table.keys() if A == top})
                on_expected(list(expected_now))
            prod_str = " ".join(prod) if prod != ["ε"] else "ε"
            print(f"使用产生式: {top} -> {prod_str}")
            stack.pop()
            if prod != ["ε"]:
                for sym in reversed(prod):
                    stack.append(sym)
    return False


# ---------------- 递归下降解析器（真实构建 AST） ----------------
class Parser:
    def __init__(self, tokens: List[Token], source_text: str = ""):
        self.tokens = list(tokens)
        self.pos = 0
        self.source_text = source_text
        self._last_expected: List[str] = []   # LL(1) 仿真阶段采集的“可能项”

    def current_token(self) -> Optional[Token]:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _tok_repr(self, tok: Optional[Token]) -> str:
        if not tok:
            return "EOF"
        return f"{tok.value}({tok.type})"

    def _format_err(self, expected: str, tok: Optional[Token]):
        if tok:
            return f"[语法错误] 期望 {expected}, 实际 {tok.value} (line={tok.line}, col={tok.column})"
        else:
            return f"[语法错误] 期望 {expected}, 实际 EOF"

    def _smart_hints(self, expected_list: List[str], got_tok: Optional[Token]) -> str:
        if not got_tok:
            return ""
        got_upper = str(got_tok.value).upper() if isinstance(got_tok.value, str) else str(got_tok.value)
        exp = set(e.upper() for e in (expected_list or []))
        prev_tok = self.tokens[self.pos - 1] if self.pos - 1 >= 0 else None
        prev2_tok = self.tokens[self.pos - 2] if self.pos - 2 >= 0 else None
        prev_upper = str(prev_tok.value).upper() if (prev_tok and isinstance(prev_tok.value, str)) else None
        prev2_upper = str(prev2_tok.value).upper() if (prev2_tok and isinstance(prev2_tok.value, str)) else None

        if "ON" in exp and got_upper in {"WHERE", "GROUP", "ORDER", "JOIN"} or ("ON" in exp and got_upper in {";", "#"}):
            return "智能提示：在 JOIN 之后应有 ON ... 条件，是否缺少连接条件？"

        if prev_upper in {"ON", "WHERE"}:
            if any(k in exp for k in {"IDENTIFIER", "(", "NOT"}) and got_upper in {"JOIN", "WHERE", "GROUP", "ORDER", ";", "#"}:
                return "智能提示：需要一个布尔条件，例如 a.id = b.sid 或 age > 18"

        if prev_upper == "BY" and prev2_upper in {"ORDER", "GROUP"}:
            if got_upper in {";", "#", "WHERE", "JOIN", "GROUP", "ORDER"} or "IDENTIFIER" in exp:
                return "智能提示：ORDER BY / GROUP BY 后应跟列名，例如 ORDER BY col 或 GROUP BY col"

        if "IDENTIFIER" in exp and got_upper == "FROM":
            return "智能提示：是否缺少选择列表？你可以写具体列名或使用 * ，例如 SELECT * FROM ..."

        return ""

    def consume(self, expected: Optional[str] = None) -> Token:
        tok = self.current_token()
        if not tok:
            raise Exception(self._format_err(expected or "TOKEN", None))

        def _raise(expected_str: str, got_tok: Optional[Token]):
            if got_tok:
                base = self._format_err(expected_str, got_tok)
                caret = caret_line(self.source_text, got_tok.line, got_tok.column, width=len(str(got_tok.value)))
                exp = self._last_expected or ([expected_str] if expected_str else [])
                hint_basic = suggest_expected_vs_got(exp, str(got_tok.value))
                msg = base + ("\n" + caret if caret else "")
                if hint_basic:
                    msg += ("\n" + hint_basic)
                smart = self._smart_hints(exp, got_tok)
                if smart:
                    msg += ("\n" + smart)
                raise Exception(msg)
            else:
                raise Exception(self._format_err(expected_str, None))

        if expected:
            up_exp = str(expected).upper()
            if up_exp in ("IDENTIFIER", "NUMBER", "STRING", "OPERATOR", "DELIMITER", "KEYWORD"):
                if getattr(tok, "type", "").upper() != up_exp:
                    if up_exp == "OPERATOR" and str(tok.value) in ("=", ">", "<", "<=", ">=", "<>"):
                        pass
                    else:
                        _raise(expected, tok)
            else:
                if isinstance(tok.value, str):
                    if tok.value.upper() != up_exp and str(tok.value) != expected:
                        if up_exp == "IDENTIFIER" and getattr(tok, "type", "").upper() == "IDENTIFIER":
                            pass
                        else:
                            _raise(expected, tok)
                else:
                    if str(tok.value) != str(expected):
                        _raise(expected, tok)

        self.pos += 1
        return tok

    def peek_token(self, k: int = 1) -> Optional[Token]:
        idx = self.pos + k
        if 0 <= idx < len(self.tokens):
            return self.tokens[idx]
        return None

    # 在每个 parse_xxx 前运行 LL1 仿真并打印（仿真使用当前剩余 token 序列）
    def run_ll1_debug(self, grammar: Dict[str, List[List[str]]], start_symbol: str, terminals: Set[str]):
        def _cap(exp):
            self._last_expected = list(exp)
        try:
            ll1_simulate(self.tokens[self.pos:], grammar, start_symbol, terminals, on_expected=_cap)
        except Exception as e:
            pass

    # 入口
    def parse(self) -> Optional[ASTNode]:
        tok = self.current_token()
        if not tok:
            return None
        kw = str(tok.value).upper() if isinstance(tok.value, str) else str(tok.value)
        if kw == "EXPLAIN":
            return self.parse_explain()
        if kw == "CREATE":
            nxt = self.peek_token(1)
            if nxt and str(nxt.value).upper() == "INDEX":
                return self.parse_create_index()
            if nxt and str(nxt.value).upper() == "DATABASE":
                return self.parse_create_database()
            return self.parse_create_table()
        if kw == "DROP":
            nxt = self.peek_token(1)
            if nxt and str(nxt.value).upper() == "INDEX":
                return self.parse_drop_index()
            if nxt and str(nxt.value).upper() == "DATABASE":
                return self.parse_drop_database()
            return self.parse_drop_table()
        if kw == "USE":
            return self.parse_use_database()
        if kw == "ALTER":
            return self.parse_alter_table()
        if kw == "TRUNCATE":
            return self.parse_truncate_table()
        if kw == "SHOW":
            nxt = self.peek_token(1)
            if nxt and str(nxt.value).upper() in ("DATABASES", "DATABASE"):
                return self.parse_show_databases()
            if nxt and str(nxt.value).upper() in ("TABLES", "TABLE"):
                return self.parse_show_tables()
            elif nxt and str(nxt.value).upper() in ("COLUMNS", "COLUMN"):
                return self.parse_show_columns()
            return self.parse_show_tables()
        if kw in ("DESC", "DESCRIBE"):
            return self.parse_describe_table()
        if kw == "INSERT":
            return self.parse_insert()
        if kw == "SELECT":
            return self.parse_select()
        if kw == "DELETE":
            return self.parse_delete()
        if kw == "UPDATE":
            return self.parse_update()
        raise Exception(f"[语法错误] 不支持的语句类型: {tok.value} (line={tok.line}, col={tok.column})")

    # ---------------- EXPLAIN ----------------
    def parse_explain(self) -> ExplainNode:
        self.consume("EXPLAIN")
        tok = self.current_token()
        if not tok or getattr(tok, "type", "") != "KEYWORD":
            raise Exception(self._format_err("CREATE/SELECT/INSERT/UPDATE/DELETE", tok))
        kw = str(tok.value).upper()
        if kw == "SELECT":
            inner = self.parse_select()
        elif kw == "CREATE":
            inner = self.parse_create_table()
        elif kw == "INSERT":
            inner = self.parse_insert()
        elif kw == "UPDATE":
            inner = self.parse_update()
        elif kw == "DELETE":
            inner = self.parse_delete()
        else:
            raise Exception(self._format_err("CREATE/SELECT/INSERT/UPDATE/DELETE", tok))
        return ExplainNode(inner)

    # ---------------- DROP TABLE ----------------
    def parse_drop_table(self) -> DropTableNode:
        self.consume("DROP")
        self.consume("TABLE")
        if_exists = False
        if self.current_token() and str(self.current_token().value).upper() == "IF":
            self.consume("IF")
            self.consume("EXISTS")
            if_exists = True
        tbl_tok = self.consume("IDENTIFIER")
        self.consume(";")
        return DropTableNode(str(tbl_tok.value), if_exists=if_exists, pos=tbl_tok.line)

    # ---------------- TRUNCATE TABLE ----------------
    def parse_truncate_table(self) -> TruncateTableNode:
        self.consume("TRUNCATE")
        if self.current_token() and str(self.current_token().value).upper() == "TABLE":
            self.consume("TABLE")
        tbl_tok = self.consume("IDENTIFIER")
        self.consume(";")
        return TruncateTableNode(str(tbl_tok.value), pos=tbl_tok.line)

    # ---------------- ALTER TABLE ----------------
    def parse_alter_table(self) -> AlterTableNode:
        self.consume("ALTER")
        self.consume("TABLE")
        tbl_tok = self.consume("IDENTIFIER")
        act_tok = self.consume()
        action = str(act_tok.value).upper()
        if action == "ADD":
            if self.current_token() and str(self.current_token().value).upper() == "COLUMN":
                self.consume("COLUMN")
            col_tok = self.consume("IDENTIFIER")
            type_tok = self.consume()
            typ = str(type_tok.value).upper()
            if self.current_token() and self.current_token().value == "(":
                self.consume("(")
                p = self.consume().value
                self.consume(")")
                typ = f"{typ}({p})"
            self.consume(";")
            return AlterTableNode(str(tbl_tok.value), "ADD", str(col_tok.value), typ, pos=tbl_tok.line)
        elif action == "DROP":
            if self.current_token() and str(self.current_token().value).upper() == "COLUMN":
                self.consume("COLUMN")
            col_tok = self.consume("IDENTIFIER")
            self.consume(";")
            return AlterTableNode(str(tbl_tok.value), "DROP", str(col_tok.value), pos=tbl_tok.line)
        else:
            raise Exception(f"[语法错误] 不支持的 ALTER TABLE 操作: {action}")

    # ---------------- CREATE INDEX ----------------
    def parse_create_index(self) -> CreateIndexNode:
        self.consume("CREATE")
        self.consume("INDEX")
        if_not_exists = False
        if self.current_token() and str(self.current_token().value).upper() == "IF":
            self.consume("IF")
            self.consume("NOT")
            self.consume("EXISTS")
            if_not_exists = True
        idx_tok = self.consume("IDENTIFIER")
        self.consume("ON")
        tbl_tok = self.consume("IDENTIFIER")
        self.consume("(")
        col_tok = self.consume("IDENTIFIER")
        self.consume(")")
        self.consume(";")
        return CreateIndexNode(str(idx_tok.value), str(tbl_tok.value), str(col_tok.value), if_not_exists=if_not_exists, pos=idx_tok.line)

    # ---------------- DROP INDEX ----------------
    def parse_drop_index(self) -> DropIndexNode:
        self.consume("DROP")
        self.consume("INDEX")
        if_exists = False
        if self.current_token() and str(self.current_token().value).upper() == "IF":
            self.consume("IF")
            self.consume("EXISTS")
            if_exists = True
        idx_tok = self.consume("IDENTIFIER")
        tbl_name = None
        if self.current_token() and str(self.current_token().value).upper() == "ON":
            self.consume("ON")
            tbl_name = str(self.consume("IDENTIFIER").value)
        self.consume(";")
        return DropIndexNode(str(idx_tok.value), tbl_name, if_exists=if_exists, pos=idx_tok.line)

    # ---------------- CREATE DATABASE ----------------
    def parse_create_database(self) -> CreateDatabaseNode:
        self.consume("CREATE")
        self.consume("DATABASE")
        if_not_exists = False
        if self.current_token() and str(self.current_token().value).upper() == "IF":
            self.consume("IF")
            self.consume("NOT")
            self.consume("EXISTS")
            if_not_exists = True
        db_tok = self.consume("IDENTIFIER")
        if self.current_token() and str(self.current_token().value) == ";":
            self.consume(";")
        return CreateDatabaseNode(str(db_tok.value), if_not_exists=if_not_exists, pos=db_tok.line)

    # ---------------- DROP DATABASE ----------------
    def parse_drop_database(self) -> DropDatabaseNode:
        self.consume("DROP")
        self.consume("DATABASE")
        if_exists = False
        if self.current_token() and str(self.current_token().value).upper() == "IF":
            self.consume("IF")
            self.consume("EXISTS")
            if_exists = True
        db_tok = self.consume("IDENTIFIER")
        if self.current_token() and str(self.current_token().value) == ";":
            self.consume(";")
        return DropDatabaseNode(str(db_tok.value), if_exists=if_exists, pos=db_tok.line)

    # ---------------- USE DATABASE ----------------
    def parse_use_database(self) -> UseDatabaseNode:
        self.consume("USE")
        if self.current_token() and str(self.current_token().value).upper() == "DATABASE":
            self.consume("DATABASE")
        db_tok = self.consume("IDENTIFIER")
        if self.current_token() and str(self.current_token().value) == ";":
            self.consume(";")
        return UseDatabaseNode(str(db_tok.value), pos=db_tok.line)

    # ---------------- SHOW DATABASES ----------------
    def parse_show_databases(self) -> ShowDatabasesNode:
        self.consume("SHOW")
        self.consume()  # DATABASES or DATABASE
        if self.current_token() and str(self.current_token().value) == ";":
            self.consume(";")
        return ShowDatabasesNode()

    # ---------------- SHOW TABLES ----------------
    def parse_show_tables(self) -> ShowTablesNode:
        self.consume("SHOW")
        self.consume()  # TABLES
        self.consume(";")
        return ShowTablesNode()

    # ---------------- DESCRIBE TABLE ----------------
    def parse_describe_table(self) -> DescribeTableNode:
        self.consume()  # DESC / DESCRIBE
        tbl_tok = self.consume("IDENTIFIER")
        self.consume(";")
        return DescribeTableNode(str(tbl_tok.value), pos=tbl_tok.line)

    # ---------------- SHOW COLUMNS FROM table ----------------
    def parse_show_columns(self) -> DescribeTableNode:
        self.consume("SHOW")
        self.consume()  # COLUMNS
        self.consume("FROM")
        tbl_tok = self.consume("IDENTIFIER")
        self.consume(";")
        return DescribeTableNode(str(tbl_tok.value), pos=tbl_tok.line)

    # ---------------- CREATE TABLE ----------------
    def parse_create_table(self) -> CreateTableNode:
        self.consume("CREATE")
        self.consume("TABLE")
        if_not_exists = False
        if self.current_token() and str(self.current_token().value).upper() == "IF":
            self.consume("IF")
            self.consume("NOT")
            self.consume("EXISTS")
            if_not_exists = True

        table_tok = self.consume("IDENTIFIER")
        table_name = table_tok.value
        self.consume("(")
        columns: List[Tuple[str, str]] = []
        constraints: List[Tuple[str, str, str, str]] = []

        def parse_def():
            t = self.current_token()
            if not t:
                raise Exception(self._format_err("DEF", None))
            up = str(t.value).upper() if isinstance(t.value, str) else str(t.value)

            # 表级 PRIMARY KEY(col)
            if up == "PRIMARY":
                self.consume("PRIMARY"); self.consume("KEY"); self.consume("(")
                pk_col = str(self.consume("IDENTIFIER").value)
                self.consume(")")
                constraints.append(("PRIMARY_KEY", pk_col, "", ""))
                return

            # FOREIGN KEY (col) REFERENCES ref_table(ref_col)
            if up == "FOREIGN":
                self.consume("FOREIGN"); self.consume("KEY"); self.consume("(")
                local_col = str(self.consume("IDENTIFIER").value)
                self.consume(")"); self.consume("REFERENCES")
                ref_table = str(self.consume("IDENTIFIER").value)
                self.consume("("); ref_col = str(self.consume("IDENTIFIER").value); self.consume(")")
                constraints.append(("FOREIGN_KEY", local_col, ref_table, ref_col))
                return

            # UNIQUE (col)
            if up == "UNIQUE" and (self.pos + 1 < len(self.tokens)) and self.tokens[self.pos + 1].value == "(":
                self.consume("UNIQUE"); self.consume("(")
                u_col = str(self.consume("IDENTIFIER").value)
                self.consume(")")
                constraints.append(("UNIQUE", u_col, "", ""))
                return

            # 列定义：IDENTIFIER TypeWithOptParam ColConstraintOpt...
            col_tok = self.consume("IDENTIFIER")
            type_tok = self.consume()
            typ = str(type_tok.value).upper()

            # 可选的 (NUMBER) 或 (NUMBER, NUMBER)
            if self.current_token() and self.current_token().value == "(":
                self.consume("(")
                p1 = self.consume().value
                if self.current_token() and self.current_token().value == ",":
                    self.consume(",")
                    p2 = self.consume().value
                    typ = f"{typ}({p1},{p2})"
                else:
                    typ = f"{typ}({p1})"
                self.consume(")")

            # 列级约束支持多项（PRIMARY KEY / NOT NULL / NULL / DEFAULT / UNIQUE）
            while self.current_token() and self.current_token().value not in (",", ")", ";"):
                tok_u = str(self.current_token().value).upper()
                if tok_u == "PRIMARY":
                    self.consume("PRIMARY")
                    self.consume("KEY")
                    constraints.append(("PRIMARY_KEY", str(col_tok.value), "", ""))
                elif tok_u == "NOT":
                    self.consume("NOT")
                    self.consume("NULL")
                    constraints.append(("NOT_NULL", str(col_tok.value), "", ""))
                elif tok_u == "NULL":
                    self.consume("NULL")
                elif tok_u == "UNIQUE":
                    self.consume("UNIQUE")
                    constraints.append(("UNIQUE", str(col_tok.value), "", ""))
                elif tok_u == "DEFAULT":
                    self.consume("DEFAULT")
                    def_val = self.consume().value
                    constraints.append(("DEFAULT", str(col_tok.value), str(def_val), ""))
                else:
                    break

            columns.append((str(col_tok.value), typ))

        parse_def()
        while self.current_token() and self.current_token().value == ",":
            self.consume(",")
            parse_def()

        self.consume(")")
        self.consume(";")
        return CreateTableNode(table_name, columns, constraints=constraints, if_not_exists=if_not_exists, pos=table_tok.line)

    # ---------------- INSERT ----------------
    def parse_insert(self) -> InsertNode:
        self.consume("INSERT")
        self.consume("INTO")
        tbl_tok = self.consume("IDENTIFIER")
        table_name = tbl_tok.value

        column_names: List[str] = []
        if self.current_token() and self.current_token().value == "(":
            self.consume("(")
            column_names.append(self.consume("IDENTIFIER").value)
            while self.current_token() and self.current_token().value == ",":
                self.consume(",")
                column_names.append(self.consume("IDENTIFIER").value)
            self.consume(")")

        self.consume("VALUES")

        def _consume_single_value():
            sign = 1
            if self.current_token() and self.current_token().value in ("-", "+"):
                op = self.consume().value
                if op == "-":
                    sign = -1
            t = self.consume()
            val = t.value
            if isinstance(val, (int, float)):
                return sign * val
            if t.type == "KEYWORD":
                u = str(val).upper()
                if u == "TRUE":
                    return True
                elif u == "FALSE":
                    return False
                elif u == "NULL":
                    return None
            elif isinstance(val, str):
                u = val.strip().upper()
                if u == "NULL":
                    return None
                elif u == "TRUE":
                    return True
                elif u == "FALSE":
                    return False
            return val

        rows: List[List[Any]] = []
        while True:
            self.consume("(")
            row: List[Any] = []
            row.append(_consume_single_value())
            while self.current_token() and self.current_token().value == ",":
                self.consume(",")
                row.append(_consume_single_value())
            self.consume(")")
            rows.append(row)
            if self.current_token() and self.current_token().value == ",":
                self.consume(",")
                continue
            break

        self.consume(";")
        return InsertNode(table_name, column_names, rows, pos=tbl_tok.line)

    # ---------------- SELECT ----------------
    def parse_select(self) -> SelectNode:
        self.consume("SELECT")

        distinct = False
        if self.current_token() and str(self.current_token().value).upper() == "DISTINCT":
            self.consume("DISTINCT")
            distinct = True

        def parse_column_ref() -> str:
            id_tok = self.consume("IDENTIFIER")
            col = str(id_tok.value).strip()
            if self.current_token() and self.current_token().value == ".":
                self.consume(".")
                right = self.consume("IDENTIFIER").value
                col = f"{col}.{str(right).strip()}"
            return col

        def parse_alias_opt() -> Optional[str]:
            if self.current_token() and isinstance(self.current_token().value, str):
                up = self.current_token().value.upper()
                if up == "AS":
                    self.consume("AS")
                    tok = self.current_token()
                    if tok and (tok.type in ("IDENTIFIER", "STRING") or getattr(tok, "type_code", 0) in (2, 3)):
                        return str(self.consume().value)
                    return str(self.consume("IDENTIFIER").value)
                if getattr(self.current_token(), "type", "") in ("IDENTIFIER", "STRING") and up not in ("FROM", "WHERE", "GROUP", "ORDER", "JOIN", "LEFT", "RIGHT", "INNER", "CROSS", "LIMIT", ";"):
                    return str(self.consume().value)
            return None

        AGG_AND_SCALAR = {
            "COUNT", "SUM", "AVG", "MAX", "MIN",
            "UPPER", "LOWER", "LENGTH", "SUBSTR", "ABS", "ROUND", "NOW"
        }

        def parse_select_item() -> Tuple[str, Optional[str]]:
            t = self.current_token()
            if not t:
                raise Exception(self._format_err("SelectItem", None))
            if isinstance(t.value, str) and t.value.upper() in AGG_AND_SCALAR:
                func = t.value.upper()
                self.consume(func)
                self.consume("(")
                if func == "COUNT" and self.current_token() and self.current_token().value == "*":
                    self.consume("*")
                    self.consume(")")
                    alias = parse_alias_opt()
                    return (f"COUNT(*)", alias)
                elif func == "NOW" and self.current_token() and self.current_token().value == ")":
                    self.consume(")")
                    alias = parse_alias_opt()
                    return ("NOW()", alias)

                first_arg = parse_column_ref() if getattr(self.current_token(), "type", "") == "IDENTIFIER" else str(self.consume().value)
                args = [first_arg]
                while self.current_token() and self.current_token().value == ",":
                    self.consume(",")
                    nxt = self.consume().value
                    args.append(str(nxt))
                self.consume(")")
                alias = parse_alias_opt()
                return (f"{func}({', '.join(args)})", alias)

            col = parse_column_ref()
            alias = parse_alias_opt()
            return (col, alias)

        select_items: List[Tuple[str, Optional[str]]] = []
        if self.current_token() and self.current_token().value == "*":
            self.consume("*")
            select_items.append(("*", None))
        else:
            select_items.append(parse_select_item())
            while self.current_token() and self.current_token().value == ",":
                self.consume(",")
                select_items.append(parse_select_item())

        self.consume("FROM")
        tbl_tok = self.consume("IDENTIFIER")
        table_name = str(tbl_tok.value).strip()
        table_alias = None
        if self.current_token() and str(self.current_token().value).upper() == "AS":
            self.consume("AS")
            table_alias = str(self.consume("IDENTIFIER").value).strip()
        elif self.current_token() and getattr(self.current_token(), "type", "").upper() == "IDENTIFIER":
            nxt = str(self.current_token().value).upper()
            if nxt not in ("JOIN", "LEFT", "RIGHT", "INNER", "CROSS", "WHERE", "GROUP", "ORDER", "LIMIT", ";"):
                table_alias = str(self.consume("IDENTIFIER").value).strip()
        if table_alias:
            table_alias = table_alias.strip().strip("()")

        joins: List[Tuple[str, Optional[str], str, str]] = []
        while self.current_token() and str(self.current_token().value).upper() in ("JOIN", "LEFT", "RIGHT", "INNER", "CROSS"):
            join_type = "INNER"
            tok_u = str(self.current_token().value).upper()
            if tok_u in ("LEFT", "RIGHT", "INNER", "CROSS"):
                join_type = tok_u
                self.consume()
                if self.current_token() and str(self.current_token().value).upper() == "OUTER":
                    self.consume("OUTER")
            self.consume("JOIN")
            right_tbl_tok = self.consume("IDENTIFIER")
            right_tbl = str(right_tbl_tok.value).strip()
            right_alias = None
            if self.current_token() and str(self.current_token().value).upper() == "AS":
                self.consume("AS")
                right_alias = str(self.consume("IDENTIFIER").value).strip()
            elif self.current_token() and getattr(self.current_token(), "type", "").upper() == "IDENTIFIER":
                nxt = str(self.current_token().value).upper()
                if nxt not in ("ON", "JOIN", "LEFT", "RIGHT", "INNER", "CROSS", "WHERE", "GROUP", "ORDER", "LIMIT", ";"):
                    right_alias = str(self.consume("IDENTIFIER").value).strip()
            if right_alias:
                right_alias = right_alias.strip().strip("()")
            cond_sql = "1=1"
            if self.current_token() and str(self.current_token().value).upper() == "ON":
                self.consume("ON")
                cond_sql = self._parse_bool_expr_sql()
            joins.append((right_tbl, right_alias, cond_sql, join_type))

        where_condition = None
        if self.current_token() and str(self.current_token().value).upper() == "WHERE":
            self.consume("WHERE")
            where_condition = self._parse_bool_expr_sql()

        group_by = None
        group_by_cols = []
        if self.current_token() and str(self.current_token().value).upper() == "GROUP":
            self.consume("GROUP")
            self.consume("BY")
            first_gb = parse_column_ref()
            group_by_cols.append(first_gb)
            while self.current_token() and self.current_token().value == ",":
                self.consume(",")
                group_by_cols.append(parse_column_ref())
            group_by = group_by_cols[0]

        having = None
        if self.current_token() and str(self.current_token().value).upper() == "HAVING":
            self.consume("HAVING")
            having = self._parse_bool_expr_sql()

        order_by = None
        order_direction = None
        if self.current_token() and str(self.current_token().value).upper() == "ORDER":
            self.consume("ORDER")
            self.consume("BY")
            order_by = parse_column_ref()
            if self.current_token() and str(self.current_token().value).upper() in ("ASC", "DESC"):
                order_direction = self.consume().value.upper()
            while self.current_token() and self.current_token().value == ",":
                self.consume(",")
                _extra_ob = parse_column_ref()
                if self.current_token() and str(self.current_token().value).upper() in ("ASC", "DESC"):
                    self.consume()

        limit = None
        offset = None
        if self.current_token() and str(self.current_token().value).upper() == "LIMIT":
            self.consume("LIMIT")
            v1 = int(self.consume("NUMBER").value)
            if self.current_token() and self.current_token().value == ",":
                self.consume(",")
                v2 = int(self.consume("NUMBER").value)
                offset = v1
                limit = v2
            elif self.current_token() and str(self.current_token().value).upper() == "OFFSET":
                self.consume("OFFSET")
                limit = v1
                offset = int(self.consume("NUMBER").value)
            else:
                limit = v1

        self.consume(";")
        node = SelectNode(select_items, table_name, from_alias=table_alias, pos=tbl_tok.line,
                          distinct=distinct, limit=limit, offset=offset, having=having)
        node.joins = joins
        node.where_condition = where_condition
        node.group_by = group_by
        node.group_by_cols = group_by_cols
        node.order_by = order_by
        node.order_direction = order_direction
        return node

    # ---- 递归式布尔表达式解析（生成原样 SQL 文本）----
    # precedence: NOT > AND > OR
    def _parse_bool_expr_sql(self) -> str:
        def parse_column_ref() -> str:
            id_tok = self.consume("IDENTIFIER")
            col = str(id_tok.value).strip()
            if self.current_token() and self.current_token().value == ".":
                self.consume(".")
                right = self.consume("IDENTIFIER").value
                col = f"{col}.{str(right).strip()}"
            return col

        def parse_value_sql() -> str:
            t = self.current_token()
            if not t:
                raise Exception(self._format_err("Value", None))

            # 支持聚合函数或标量函数: AVG(e.salary), COUNT(*), SUM(...)
            AGG_FUNCS = {"COUNT", "SUM", "AVG", "MAX", "MIN", "ROUND", "ABS", "UPPER", "LOWER", "LENGTH"}
            if t and isinstance(t.value, str) and t.value.upper() in AGG_FUNCS and (self.pos + 1 < len(self.tokens)) and self.tokens[self.pos + 1].value == "(":
                fn_name = str(self.consume().value).upper()
                self.consume("(")
                if fn_name == "COUNT" and self.current_token() and self.current_token().value == "*":
                    self.consume("*")
                    self.consume(")")
                    return "COUNT(*)"
                arg_sql = parse_value_sql()
                while self.current_token() and self.current_token().value == ",":
                    self.consume(",")
                    arg_sql += f", {parse_value_sql()}"
                self.consume(")")
                return f"{fn_name}({arg_sql})"

            if getattr(t, "type", "") == "IDENTIFIER":
                if (self.pos + 1) < len(self.tokens) and self.tokens[self.pos + 1].value == ".":
                    return parse_column_ref()
                return self.consume("IDENTIFIER").value
            if getattr(t, "type", "") == "NUMBER":
                return str(self.consume("NUMBER").value)
            if getattr(t, "type", "") == "STRING":
                v = self.consume("STRING").value
                return f"'{v}'"
            if t.value == "(":
                self.consume("(")
                inner = parse_bool_expr()
                self.consume(")")
                return f"({inner})"
            if str(t.value).upper() in ("NULL", "TRUE", "FALSE"):
                return str(self.consume().value).upper()
            return parse_column_ref()

        def parse_predicate() -> str:
            left = parse_value_sql()
            t = self.current_token()
            if not t:
                return left
            val_u = str(t.value).upper()

            # 1) IS [NOT] NULL
            if val_u == "IS":
                self.consume("IS")
                if self.current_token() and str(self.current_token().value).upper() == "NOT":
                    self.consume("NOT")
                    self.consume("NULL")
                    return f"{left} IS NOT NULL"
                self.consume("NULL")
                return f"{left} IS NULL"

            # 2) [NOT] LIKE
            if val_u == "LIKE":
                self.consume("LIKE")
                pat = parse_value_sql()
                return f"{left} LIKE {pat}"
            if val_u == "NOT" and (self.pos + 1 < len(self.tokens)) and str(self.tokens[self.pos + 1].value).upper() == "LIKE":
                self.consume("NOT")
                self.consume("LIKE")
                pat = parse_value_sql()
                return f"{left} NOT LIKE {pat}"

            # 3) [NOT] IN (...)
            if val_u == "IN":
                self.consume("IN")
                self.consume("(")
                vals = [parse_value_sql()]
                while self.current_token() and self.current_token().value == ",":
                    self.consume(",")
                    vals.append(parse_value_sql())
                self.consume(")")
                return f"{left} IN ({', '.join(vals)})"
            if val_u == "NOT" and (self.pos + 1 < len(self.tokens)) and str(self.tokens[self.pos + 1].value).upper() == "IN":
                self.consume("NOT")
                self.consume("IN")
                self.consume("(")
                vals = [parse_value_sql()]
                while self.current_token() and self.current_token().value == ",":
                    self.consume(",")
                    vals.append(parse_value_sql())
                self.consume(")")
                return f"{left} NOT IN ({', '.join(vals)})"

            # 4) [NOT] BETWEEN low AND high
            if val_u == "BETWEEN":
                self.consume("BETWEEN")
                low = parse_value_sql()
                self.consume("AND")
                high = parse_value_sql()
                return f"{left} BETWEEN {low} AND {high}"
            if val_u == "NOT" and (self.pos + 1 < len(self.tokens)) and str(self.tokens[self.pos + 1].value).upper() == "BETWEEN":
                self.consume("NOT")
                self.consume("BETWEEN")
                low = parse_value_sql()
                self.consume("AND")
                high = parse_value_sql()
                return f"{left} NOT BETWEEN {low} AND {high}"

            # 5) 标准关系比较: =, >, <, >=, <=, !=, <>
            op_tok = self.consume()
            op = str(op_tok.value)
            right = parse_value_sql()
            return f"{left} {op} {right}"

        def parse_bool_factor() -> str:
            t = self.current_token()
            if t and isinstance(t.value, str) and t.value.upper() == "NOT":
                self.consume("NOT")
                f = parse_bool_factor()
                return f"(NOT {f})"
            if t and t.value == "(":
                self.consume("(")
                e = parse_bool_expr()
                self.consume(")")
                return f"({e})"
            return parse_predicate()

        def parse_bool_term() -> str:
            left = parse_bool_factor()
            while self.current_token() and isinstance(self.current_token().value, str) and self.current_token().value.upper() == "AND":
                self.consume("AND")
                right = parse_bool_factor()
                left = f"({left} AND {right})"
            return left

        def parse_bool_expr() -> str:
            left = parse_bool_term()
            while self.current_token() and isinstance(self.current_token().value, str) and self.current_token().value.upper() == "OR":
                self.consume("OR")
                right = parse_bool_term()
                left = f"({left} OR {right})"
            return left

        return parse_bool_expr()

    # ---------------- DELETE ----------------
    def parse_delete(self) -> DeleteNode:
        self.consume("DELETE")
        self.consume("FROM")
        t = self.consume("IDENTIFIER")
        node = DeleteNode(t.value, pos=t.line)
        if self.current_token() and str(self.current_token().value).upper() == "WHERE":
            self.consume("WHERE")
            node.where_condition = self._parse_bool_expr_sql()
        self.consume(";")
        return node

    # ---------------- UPDATE ----------------
    def parse_update(self) -> UpdateNode:
        self.consume("UPDATE")
        tbl_tok = self.consume("IDENTIFIER")
        table_name = tbl_tok.value

        self.consume("SET")
        assignments: List[Tuple[str, Any]] = []

        def parse_value_any():
            if self.current_token() and getattr(self.current_token(), "type", "").upper() == "IDENTIFIER":
                if (self.pos + 1) < len(self.tokens) and self.tokens[self.pos + 1].value == ".":
                    left = str(self.consume("IDENTIFIER").value).strip()
                    self.consume(".")
                    right = str(self.consume("IDENTIFIER").value).strip()
                    return f"{left}.{right}"
                else:
                    return self.consume("IDENTIFIER").value
            else:
                t = self.consume()
                return t.value

        col = str(self.consume("IDENTIFIER").value).strip()
        if self.current_token() and self.current_token().value == "=":
            self.consume("=")
        else:
            self.consume("OPERATOR")
        val = parse_value_any()
        assignments.append((col, val))

        while self.current_token() and self.current_token().value == ",":
            self.consume(",")
            col = str(self.consume("IDENTIFIER").value).strip()
            if self.current_token() and self.current_token().value == "=":
                self.consume("=")
            else:
                self.consume("OPERATOR")
            val = parse_value_any()
            assignments.append((col, val))

        node = UpdateNode(table_name, assignments, pos=tbl_tok.line)

        if self.current_token() and str(self.current_token().value).upper() == "WHERE":
            self.consume("WHERE")
            node.where_condition = self._parse_bool_expr_sql()

        self.consume(";")
        return node
