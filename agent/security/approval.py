# agent/security/approval.py
import uuid
import time
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from agent.tools.base import RiskLevel


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    TIMED_OUT = "TIMED_OUT"


class ApprovalRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    task_id: str
    session_id: str = "default"
    sql: str
    risk_level: RiskLevel
    statement_type: str
    reason: str
    created_at: float = Field(default_factory=time.time)
    status: ApprovalStatus = ApprovalStatus.PENDING


class ApprovalManager:
    """
    人工审批中心 (Human-in-the-loop Approval Manager)
    支持 ADMIN/DDL 操作挂起与 Web/API 审批交互
    """

    def __init__(self):
        self._requests: Dict[str, ApprovalRequest] = {}

    def create_request(
        self,
        task_id: str,
        session_id: str,
        sql: str,
        risk_level: RiskLevel,
        statement_type: str,
        reason: str
    ) -> ApprovalRequest:
        req = ApprovalRequest(
            task_id=task_id,
            session_id=session_id,
            sql=sql,
            risk_level=risk_level,
            statement_type=statement_type,
            reason=reason
        )
        self._requests[req.request_id] = req
        return req

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        return self._requests.get(request_id)

    def get_by_task(self, task_id: str) -> Optional[ApprovalRequest]:
        for req in self._requests.values():
            if req.task_id == task_id:
                return req
        return None

    def list_pending(self) -> List[ApprovalRequest]:
        return [r for r in self._requests.values() if r.status == ApprovalStatus.PENDING]

    def approve(self, request_id: str) -> bool:
        req = self._requests.get(request_id)
        if req and req.status == ApprovalStatus.PENDING:
            req.status = ApprovalStatus.APPROVED
            return True
        return False

    def reject(self, request_id: str) -> bool:
        req = self._requests.get(request_id)
        if req and req.status == ApprovalStatus.PENDING:
            req.status = ApprovalStatus.REJECTED
            return True
        return False
