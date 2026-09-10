# agent/tools/base.py
from enum import Enum
from typing import List, Optional, Callable, Any
from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    READ = "READ"            # 读操作：SELECT, SHOW, EXPLAIN (自动放行)
    WRITE = "WRITE"          # 写操作：INSERT, UPDATE, DELETE (按策略放行)
    ADMIN = "ADMIN"          # 运维操作：CREATE INDEX, CREATE TABLE, ALTER TABLE (默认需审批)
    DANGEROUS = "DANGEROUS"  # 高危操作：DROP TABLE, TRUNCATE TABLE (默认拦截)


class ToolSpec(BaseModel):
    """CortexDB Tool 元数据规范"""
    name: str
    description: str
    risk_level: RiskLevel = RiskLevel.READ
    permissions: List[str] = Field(default_factory=lambda: ["sql.read"])
    timeout: float = 30.0
    retryable: bool = False
