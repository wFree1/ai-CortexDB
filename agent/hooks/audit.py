# agent/hooks/audit.py
import time
from typing import Dict, List, Any
from pydantic import BaseModel, Field
from agent.hooks.base import BaseHook


class AuditRecord(BaseModel):
    timestamp: float = Field(default_factory=time.time)
    task_id: str
    action: str
    sql: str
    status: str
    latency_ms: float = 0.0
    details: Dict[str, Any] = Field(default_factory=dict)


class AuditHook(BaseHook):
    """
    审计 Hook (Audit Hook)
    永久记录数据库操作轨迹、SQL 执行与安全审批事件
    """

    def __init__(self, max_records: int = 1000):
        self.max_records = max_records
        self._records: List[AuditRecord] = []

    def after_sql(self, task_id: str, sql: str, success: bool, latency_ms: float) -> None:
        rec = AuditRecord(
            task_id=task_id,
            action="SQL_EXECUTION",
            sql=sql,
            status="SUCCESS" if success else "FAILED",
            latency_ms=latency_ms
        )
        self._records.append(rec)
        if len(self._records) > self.max_records:
            self._records.pop(0)

    def on_approval(self, task_id: str, request_id: str, sql: str, status: str) -> None:
        rec = AuditRecord(
            task_id=task_id,
            action="SECURITY_APPROVAL",
            sql=sql,
            status=status,
            details={"request_id": request_id}
        )
        self._records.append(rec)
        if len(self._records) > self.max_records:
            self._records.pop(0)

    def get_audit_trail(self, limit: int = 50) -> List[Dict[str, Any]]:
        return [r.model_dump() for r in reversed(self._records[-limit:])]
