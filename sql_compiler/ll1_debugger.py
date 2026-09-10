from __future__ import annotations
from typing import List, Dict, Set, Tuple, Callable, Optional, Any

# -------------- 实用类型 --------------
TokenLike = Any  # 兼容你的 Token（有 .type / .value / .line / .column）

# -------------- Debug 打印（可替换） --------------
def _default_print(s: str) -> None:
    print(s)

# -------------- LL(1) 调试器 --------------
class LL1ParserDebugger:
    """
    用法：
      dbg = LL1ParserDebugger(tokens, grammar, start, terminals, non_terminals,
                              banner="[LL1 推导过程]", banner_once_key="GLOBAL",
                              print_func=print, show_banner=True)
      ok = dbg.run()

    关键特性：
      - 计算 FIRST / FOLLOW / 预测表，按 LL(1) 栈机进行推导并打印每一步
      - 发生错误时，给出期望集合与“期望/实际”
      - 防止“系统栏连续两个 debug 语句”：同一 banner_once_key 只打印一次横幅
    """
    # class 级的横幅已打印集合，用于一次进程内去重
    _printed_banners: Set[str] = set()

    def __init__(
        self,
        tokens: List[TokenLike],
        grammar: Dict[str, List[List[str]]],
        start_symbol: str,
        terminals: Set[str],
        non_terminals: Set[str],
        *,
        banner: str = "[LL1 推导过程]",
        banner_once_key: Optional[str] = "GLOBAL",
        print_func: Callable[[str], None] = _default_print,
        show_banner: bool = True,
        align_width: int = 70
    ):
        self.tokens = list(tokens or [])
        self.grammar = grammar
        self.start = start_symbol
        self.terminals = set(terminals or set())
        self.non_terminals = set(non_terminals or set())
        self.banner = banner
        self.banner_once_key = banner_once_key
        self.print = print_func
        self.show_banner = show_banner
        self.align = align_width

        # 运行中产物
        self.FIRST: Dict[str, Set[str]] = {}
        self.FOLLOW: Dict[str, Set[str]] = {}
        self.parse_table: Dict[Tuple[str, str], List[str]] = {}
        self._last_expected: List[str] = []  # 对外可用：最近一步的期望项

    # ---------------- 公共入口 ----------------
    def run(self) -> bool:
        # 打印横幅（一次进程只打印一次，或关闭）
        if self.show_banner and self.banner:
            key = self.banner_once_key or id(self)
            if key not in LL1ParserDebugger._printed_banners:
                self.print(f"\n{self.banner}")
                LL1ParserDebugger._printed_banners.add(key)

        # 计算集合与预测表
        self.FIRST = self._compute_first_sets()
        self.FOLLOW = self._compute_follow_sets()
        self.parse_table = self._build_parse_table()

        # 输入符号流：把 Token 映射为文法终结符
        input_symbols = [self._tok_to_sym(t) for t in self.tokens] + ["#"]
        stack: List[str] = ["#", self.start]

        def s_stack():  return " ".join(stack)
        def s_input():  return " ".join(input_symbols)

        ip = 0
        while stack:
            top = stack[-1]
            cur = input_symbols[ip] if ip < len(input_symbols) else "#"

            self.print(f"栈: {s_stack():<{self.align}} 输入: {s_input():<{self.align}} # 处理: {top}")

            # 接受
            if top == "#":
                if cur == "#":
                    self.print("[OK] 输入完整匹配，分析成功")
                    return True
                self.print(f"[FAIL] 出错: 栈到达底 (#)，但输入尚未结束 -> {cur}")
                return False

            # 匹配终结符
            if top in self.terminals:
                if top == cur:
                    stack.pop(); ip += 1
                    continue
                # 终结符不一致 -> 错误
                tok = self._cur_token_safe(ip)
                self._report_expect(top, cur, tok)
                return False

            # 非终结符：查预测表
            prod = self.parse_table.get((top, cur))
            if prod is None:
                expected = sorted({a for (A, a) in self.parse_table.keys() if A == top})
                self._last_expected = expected
                tok = self._cur_token_safe(ip)
                self._report_table_miss(top, cur, expected, tok)
                return False

            # 打印产生式
            self._last_expected = sorted({a for (A, a) in self.parse_table.keys() if A == top})
            prod_str = " ".join(prod) if prod != ["ε"] else "ε"
            self.print(f"使用产生式: {top} -> {prod_str}")
            stack.pop()
            if prod != ["ε"]:
                for sym in reversed(prod):
                    stack.append(sym)

        return False

    # ---------------- 工具：Token -> 符号 ----------------
    def _tok_to_sym(self, tok: Optional[TokenLike]) -> str:
        if tok is None:
            return "#"
        ttype = getattr(tok, "type", "")
        tval = getattr(tok, "value", None)

        # 关键字直接作为大写关键字
        if ttype == "KEYWORD":
            v = str(tval).upper()
            return v

        # 其余按类别 / 文法中的终结符来
        if ttype in ("IDENTIFIER", "NUMBER", "STRING", "OPERATOR", "DELIMITER"):
            if ttype == "DELIMITER":
                if tval in ("(", ")", ",", ";", ".", "*"):
                    return tval
                if tval == "=":
                    return "OPERATOR"
            return ttype

        # 兜底
        if isinstance(tval, str):
            return tval.upper()
        return str(tval)

    # ---------------- FIRST / FOLLOW / 预测表 ----------------
    def _compute_first_sets(self) -> Dict[str, Set[str]]:
        FIRST: Dict[str, Set[str]] = {nt: set() for nt in self.grammar}
        changed = True
        while changed:
            changed = False
            for A, prods in self.grammar.items():
                for prod in prods:
                    if prod == ["ε"] or len(prod) == 0:
                        if "ε" not in FIRST[A]:
                            FIRST[A].add("ε"); changed = True
                        continue
                    add_eps = True
                    for X in prod:
                        if X in self.terminals:
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
                                break
                    if add_eps:
                        if "ε" not in FIRST[A]:
                            FIRST[A].add("ε"); changed = True
        return FIRST

    def _compute_follow_sets(self) -> Dict[str, Set[str]]:
        FOLLOW: Dict[str, Set[str]] = {nt: set() for nt in self.grammar}
        FOLLOW[self.start].add("#")
        changed = True
        while changed:
            changed = False
            for A, prods in self.grammar.items():
                for prod in prods:
                    for i, B in enumerate(prod):
                        if B not in self.grammar:
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
                                if sym in self.terminals:
                                    first_beta.add(sym); contains_eps = False; break
                                else:
                                    first_beta.update(x for x in self.FIRST.get(sym, set()) if x != "ε")
                                    if "ε" in self.FIRST.get(sym, set()):
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

    def _build_parse_table(self) -> Dict[Tuple[str, str], List[str]]:
        table: Dict[Tuple[str, str], List[str]] = {}
        for A, prods in self.grammar.items():
            for prod in prods:
                first_prod = set()
                if prod == ["ε"] or len(prod) == 0:
                    first_prod.add("ε")
                else:
                    contains_eps = True
                    for sym in prod:
                        if sym in self.terminals:
                            first_prod.add(sym); contains_eps = False; break
                        else:
                            first_prod.update(x for x in self.FIRST.get(sym, set()) if x != "ε")
                            if "ε" in self.FIRST.get(sym, set()):
                                contains_eps = True
                            else:
                                contains_eps = False; break
                    if contains_eps:
                        first_prod.add("ε")
                for a in first_prod:
                    if a != "ε":
                        table[(A, a)] = prod
                if "ε" in first_prod:
                    for b in self.FOLLOW.get(A, set()):
                        table[(A, b)] = prod
        return table

    # ---------------- 错误呈现 ----------------
    def _cur_token_safe(self, ip: int) -> Optional[TokenLike]:
        return self.tokens[ip] if ip < len(self.tokens) else None

    def _report_expect(self, expected: str, actual: str, tok: Optional[TokenLike]) -> None:
        if tok is not None:
            self.print(f"[FAIL] 出错: 期望 {expected}, 实际 {actual} (line={getattr(tok,'line', '?')}, col={getattr(tok,'column','?')})")
        else:
            self.print(f"[FAIL] 出错: 期望 {expected}, 实际 EOF")

    def _report_table_miss(self, top: str, cur: str, expected_list: List[str], tok: Optional[TokenLike]) -> None:
        exp_str = ", ".join(expected_list) if expected_list else "N/A"
        if tok is not None:
            self.print(f"[FAIL] 出错: 无法从 {top} 推导输入 {cur}")
            self.print(f"[语法错误] 期望其中之一: {exp_str}, 实际 {cur} (line={getattr(tok,'line','?')}, col={getattr(tok,'column','?')})")
        else:
            self.print(f"[FAIL] 出错: 无法从 {top} 推导输入 EOF")

    # ---------------- 可选：对外取最近一次期望集合 ----------------
    def last_expected(self) -> List[str]:
        return list(self._last_expected)
