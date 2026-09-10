# 智能纠错提示
from typing import Iterable, Optional, Tuple, List

def levenshtein(a: str, b: str) -> int:
    if a == b: return 0
    if not a: return len(b)
    if not b: return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            c = 0 if ca == cb else 1
            cur.append(min(prev[j] + 1, cur[j-1] + 1, prev[j-1] + c))
        prev = cur
    return prev[-1]

def nearest(word: str, candidates: Iterable[str], max_dist: int = 2) -> Optional[str]:
    word_up = str(word).upper()
    best = None
    best_d = max_dist + 1
    for c in candidates:
        d = levenshtein(word_up, str(c).upper())
        if d < best_d:
            best_d, best = d, c
    return best if best_d <= max_dist else None

def caret_line(source: str, line: int, col: int, width: int = 1) -> str:
    lines = source.splitlines() or [source]
    if line - 1 < 0 or line - 1 >= len(lines): return ""
    s = lines[line - 1]
    pointer = " " * max(0, col - 1) + "^" + ("~" * max(0, width - 1))
    return s + "\n" + pointer

def suggest_expected_vs_got(expected: Iterable[str], got: str) -> str:
    exp = list(dict.fromkeys([str(e) for e in expected]))  # 去重保持序
    if not exp: return ""
    hint = []
    near = nearest(got, exp, max_dist=2)
    if near:
        hint.append(f"你是否想写 '{near}' ？")
    return ("可能的输入：[" + ", ".join(exp[:10]) + (", ..." if len(exp) > 10 else "") + "]"
            + (f"\n提示：{hint[0]}" if hint else ""))

def suggest_alias(got: str, aliases: Iterable[str]) -> str:
    cand = nearest(got, aliases, 2)
    if cand:
        return f"你是否想写别名 '{cand}' ？（当前可用别名：{', '.join(aliases)}）"
    return f"当前可用别名：{', '.join(aliases)}" if aliases else ""
