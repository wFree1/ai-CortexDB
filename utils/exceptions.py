# utils/exceptions.py
from typing import Optional, List, Any


class DataSphereError(Exception):
    """DataSphere 数据库系统的基类异常"""
    def __init__(self, message: str, smart_hints: Optional[List[str]] = None):
        super().__init__(message)
        self.message = message
        self.smart_hints = smart_hints or []

    def __str__(self):
        if self.smart_hints:
            hints_str = "\n".join(f"  - {h}" for h in self.smart_hints)
            return f"{self.message}\n智能提示:\n{hints_str}"
        return self.message


class SQLSyntaxError(DataSphereError):
    """SQL 词法分析与语法分析异常"""
    def __init__(self, message: str, line: Optional[int] = None, col: Optional[int] = None, smart_hints: Optional[List[str]] = None):
        super().__init__(message, smart_hints)
        self.line = line
        self.col = col


class SemanticError(DataSphereError):
    """SQL 语义分析异常（如表不存在、列不存在、类型不匹配、聚合使用不当等）"""
    pass


class ConstraintViolationError(DataSphereError):
    """数据库完整性约束异常（主键重复、外键引用不存在等）"""
    pass


class StorageError(DataSphereError):
    """底层存储与缓冲池操作异常"""
    pass


class ExecutionError(DataSphereError):
    """执行计划在物理执行期间发生的运行时异常"""
    pass
