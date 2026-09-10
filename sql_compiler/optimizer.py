# 谓词下推（Predicate Pushdown）优化
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple, Union

# ---- 计划节点定义（和 planner 中一致）----
@dataclass
class PlanNode:
    def output_aliases(self) -> Set[str]:
        return set()

@dataclass
class SeqScanOp(PlanNode):
    table: str
    alias: Optional[str] = None
    def __repr__(self):
        if self.alias and self.alias != self.table:
            return f"SeqScanOp({self.table} AS {self.alias})"
        return f"SeqScanOp({self.table})"
    def output_aliases(self) -> Set[str]:
        return {self.alias or self.table}

@dataclass
class FilterOp(PlanNode):
    child: PlanNode
    predicate: str
    def __repr__(self):
        return f"FilterOp({self.child}, {self.predicate})"
    def output_aliases(self) -> Set[str]:
        return self.child.output_aliases()

@dataclass
class ProjectOp(PlanNode):
    child: PlanNode
    columns: List[str]
    def __repr__(self):
        return f"ProjectOp({self.child}, {self.columns})"
    def output_aliases(self) -> Set[str]:
        return self.child.output_aliases()

@dataclass
class SortOp(PlanNode):
    child: PlanNode
    order_by: str
    direction: Optional[str] = None  # "ASC"/"DESC"/None
    def __repr__(self):
        dir_part = f" {self.direction}" if self.direction else ""
        return f"SortOp({self.child}, ORDER BY {self.order_by}{dir_part})"
    def output_aliases(self) -> Set[str]:
        return self.child.output_aliases()

@dataclass
class JoinOp(PlanNode):
    left: PlanNode
    right: PlanNode
    condition: str  # 连接条件字符串
    def __repr__(self):
        return f"JoinOp({self.left}, {self.right}, ON {self.condition})"
    def output_aliases(self) -> Set[str]:
        return self.left.output_aliases() | self.right.output_aliases()


# ---- 工具函数 ----
def _split_conjuncts(pred: str) -> List[str]:
    """
    极简 AND 拆分：按小写/大写 AND 分割；不处理括号与 OR（足够覆盖你当前示例）
    """
    parts: List[str] = []
    buf = []
    tokens = pred.replace("&&", "AND").split()
    i = 0
    while i < len(tokens):
        if tokens[i].upper() == "AND":
            if buf:
                parts.append(" ".join(buf))
                buf = []
        else:
            buf.append(tokens[i])
        i += 1
    if buf:
        parts.append(" ".join(buf))
    return [p.strip() for p in parts if p.strip()]


def _used_aliases(expr: str) -> Set[str]:
    """
    从表达式里提取使用到的别名（形如 a.col）。未加点的列名无法精确判断归属，返回空。
    """
    aliases = set()
    for tok in expr.replace("=", " ").replace("<", " ").replace(">", " ").replace("!", " ").replace("(", " ").replace(")", " ").replace(",", " ").split():
        if "." in tok:
            a, _ = tok.split(".", 1)
            aliases.add(a)
    return aliases


def _can_push_to(child: PlanNode, pred: str) -> bool:
    """
    规则：若谓词中的所有带点列的别名都包含在 child 的输出别名集合中，则可下推到该 child。
    对于不带点的列名，这里保守起见不下推（避免歧义）。
    """
    used = _used_aliases(pred)
    outs = child.output_aliases()
    return bool(used) and used.issubset(outs)


def _merge_filters(node: PlanNode) -> PlanNode:
    """把相邻的 Filter 合并为一个 AND 谓词。"""
    if isinstance(node, FilterOp) and isinstance(node.child, FilterOp):
        merged = FilterOp(node.child.child, f"{node.child.predicate} AND {node.predicate}")
        return _merge_filters(merged)
    return node


# ---- 核心：谓词下推 ----
def predicate_pushdown(node: PlanNode) -> PlanNode:
    """
    递归优化：
    - Filter ⬌ Sort：Filter 下沉到 Sort 之下
    - Filter ⬌ Project：若投影保留了谓词所需列，Filter 下沉
    - Filter ⬌ Join：按 AND 拆分，能下推到左/右的分别下推，剩余保留在 Join 上方
    - 合并相邻 Filter
    """
    # 先递归优化子树
    if isinstance(node, FilterOp):
        child = predicate_pushdown(node.child)

        # Filter over Sort => 下沉
        if isinstance(child, SortOp):
            pushed = FilterOp(child.child, node.predicate)
            new_child = SortOp(predicate_pushdown(pushed), child.order_by, child.direction)
            return _merge_filters(new_child)

        # Filter over Project => 仅当 Project 保留了谓词涉及的列（保守：要求谓词里所有 a.col 都在columns中，或别名出现在输出别名中）
        if isinstance(child, ProjectOp):
            used = _used_aliases(node.predicate)
            cols = set(child.columns)
            # 如果是带别名的列（a.col），直接检查字符串是否在投影列表里
            if used and all(any(c.endswith("." + token.split(".", 1)[1]) or c == token for c in cols) for token in used):
                pushed = FilterOp(child.child, node.predicate)
                return ProjectOp(predicate_pushdown(pushed), child.columns)
            # 否则保守不动
            return FilterOp(predicate_pushdown(child), node.predicate)

        # Filter over Join => 拆分 AND，分别下推至左右
        if isinstance(child, JoinOp):
            conjuncts = _split_conjuncts(node.predicate)
            left_push: List[str] = []
            right_push: List[str] = []
            remain: List[str] = []
            for c in conjuncts:
                if _can_push_to(child.left, c):
                    left_push.append(c)
                elif _can_push_to(child.right, c):
                    right_push.append(c)
                else:
                    remain.append(c)

            new_left = predicate_pushdown(FilterOp(child.left, " AND ".join(left_push))) if left_push else predicate_pushdown(child.left)
            new_right = predicate_pushdown(FilterOp(child.right, " AND ".join(right_push))) if right_push else predicate_pushdown(child.right)
            new_join = JoinOp(new_left, new_right, child.condition)

            if remain:
                return FilterOp(new_join, " AND ".join(remain))
            return new_join

        # 其他：递归并合并 filter
        return _merge_filters(FilterOp(child, node.predicate))

    elif isinstance(node, ProjectOp):
        return ProjectOp(predicate_pushdown(node.child), node.columns)

    elif isinstance(node, SortOp):
        return SortOp(predicate_pushdown(node.child), node.order_by, node.direction)

    elif isinstance(node, JoinOp):
        return JoinOp(predicate_pushdown(node.left), predicate_pushdown(node.right), node.condition)

    else:
        return node
