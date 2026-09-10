# agent/security/risk.py
from typing import Optional, Dict, Any, Tuple
from agent.tools.base import RiskLevel
from sql_compiler.lexer import Lexer
from sql_compiler.parser import (
    Parser,
    SelectNode,
    ExplainNode,
    InsertNode,
    UpdateNode,
    DeleteNode,
    CreateTableNode,
    AlterTableNode,
    DropTableNode,
    TruncateTableNode
)

# 某些节点可能为动态导入或不存在
try:
    from sql_compiler.parser import CreateIndexNode, DropIndexNode, ShowTablesNode
except ImportError:
    CreateIndexNode = None
    DropIndexNode = None
    ShowTablesNode = None


class RiskAssessment(object):
    def __init__(self, risk_level: RiskLevel, statement_type: str, reason: str, ast_node: Any = None):
        self.risk_level = risk_level
        self.statement_type = statement_type
        self.reason = reason
        self.ast_node = ast_node

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_level": self.risk_level.value,
            "statement_type": self.statement_type,
            "reason": self.reason
        }


class RiskClassifier:
    """
    基于 AST 语法树的确定性 SQL 风险分类引擎
    坚决不使用弱正则/子串匹配（如 if 'drop' in sql），严格解析语法树节点类型
    """

    @classmethod
    def evaluate(cls, sql: str) -> RiskAssessment:
        sql = sql.strip()
        if not sql:
            return RiskAssessment(RiskLevel.READ, "EMPTY", "空语句")

        try:
            tokens = Lexer(sql).tokens
            ast = Parser(tokens).parse()
        except Exception as e:
            # 无法解析时标记为未知风险
            return RiskAssessment(
                RiskLevel.DANGEROUS,
                "UNPARSEABLE",
                f"SQL 无法被解析为合法语法树: {e}"
            )

        # 1. READ: SELECT, EXPLAIN, SHOW
        if isinstance(ast, SelectNode):
            return RiskAssessment(RiskLevel.READ, "SELECT", "只读查询，无数据变更风险", ast)
        if isinstance(ast, ExplainNode):
            return RiskAssessment(RiskLevel.READ, "EXPLAIN", "只读执行计划分析", ast)
        if ShowTablesNode and isinstance(ast, ShowTablesNode):
            return RiskAssessment(RiskLevel.READ, "SHOW", "只读元数据查看", ast)

        # 2. WRITE: INSERT, UPDATE, DELETE
        if isinstance(ast, InsertNode):
            return RiskAssessment(RiskLevel.WRITE, "INSERT", "数据行插入操作", ast)
        if isinstance(ast, UpdateNode):
            return RiskAssessment(RiskLevel.WRITE, "UPDATE", "数据行更新操作", ast)
        if isinstance(ast, DeleteNode):
            return RiskAssessment(RiskLevel.WRITE, "DELETE", "数据行删除操作", ast)

        # 3. ADMIN: CREATE TABLE, ALTER TABLE, CREATE INDEX, DROP INDEX
        if isinstance(ast, CreateTableNode):
            return RiskAssessment(RiskLevel.ADMIN, "CREATE_TABLE", "结构定义变更 (DDL)", ast)
        if isinstance(ast, AlterTableNode):
            return RiskAssessment(RiskLevel.ADMIN, "ALTER_TABLE", "结构修改变更 (DDL)", ast)
        if CreateIndexNode and isinstance(ast, CreateIndexNode):
            return RiskAssessment(RiskLevel.ADMIN, "CREATE_INDEX", "索引创建运维操作", ast)
        if DropIndexNode and isinstance(ast, DropIndexNode):
            return RiskAssessment(RiskLevel.ADMIN, "DROP_INDEX", "索引销毁运维操作", ast)

        # 4. DANGEROUS: DROP TABLE, TRUNCATE TABLE
        if isinstance(ast, DropTableNode):
            return RiskAssessment(RiskLevel.DANGEROUS, "DROP_TABLE", "高危物理表删除操作，可能造成数据永久丢失", ast)
        if isinstance(ast, TruncateTableNode):
            return RiskAssessment(RiskLevel.DANGEROUS, "TRUNCATE_TABLE", "高危全表清空操作", ast)

        # 兜底
        return RiskAssessment(RiskLevel.ADMIN, "UNKNOWN_STMT", "未知类型语句，默认按 ADMIN 谨慎处理", ast)
