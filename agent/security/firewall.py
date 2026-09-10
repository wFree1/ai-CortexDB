# agent/security/firewall.py
from typing import Dict, Any, Optional
from agent.tools.base import RiskLevel
from agent.security.policy import SecurityPolicy
from agent.security.risk import RiskClassifier, RiskAssessment
from agent.security.approval import ApprovalManager, ApprovalRequest, ApprovalStatus


class FirewallDecision:
    def __init__(
        self,
        allowed: bool,
        action: str,  # "ALLOW", "DENY", "REQUIRE_APPROVAL"
        risk: RiskAssessment,
        reason: str,
        approval_request: Optional[ApprovalRequest] = None
    ):
        self.allowed = allowed
        self.action = action
        self.risk = risk
        self.reason = reason
        self.approval_request = approval_request

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "action": self.action,
            "risk_level": self.risk.risk_level.value,
            "statement_type": self.risk.statement_type,
            "reason": self.reason,
            "approval_required": self.action == "REQUIRE_APPROVAL",
            "approval_request_id": self.approval_request.request_id if self.approval_request else None
        }


class SQLFirewall:
    """
    CortexDB 原生 SQL 确定性安全防火墙
    在 SQL 进入编译器和执行器之前完成 AST 风险评估、权限策略匹配与人工审批判定。
    """

    def __init__(self, policy: Optional[SecurityPolicy] = None, approval_mgr: Optional[ApprovalManager] = None):
        self.policy = policy or SecurityPolicy.from_config()
        self.approval_mgr = approval_mgr or ApprovalManager()

    def inspect(self, sql: str, task_id: str = "default", session_id: str = "default") -> FirewallDecision:
        risk = RiskClassifier.evaluate(sql)

        # 1. DANGEROUS 操作一律拒绝 (如 DROP TABLE, TRUNCATE TABLE)
        if risk.risk_level == RiskLevel.DANGEROUS and self.policy.deny_dangerous_always:
            return FirewallDecision(
                allowed=False,
                action="DENY",
                risk=risk,
                reason=f"拦截高危危险操作: {risk.reason}。该语句已被 SQL 防火墙主动阻断。"
            )

        # 2. READ 操作默认直接放行 (SELECT, EXPLAIN, SHOW)
        if risk.risk_level == RiskLevel.READ:
            return FirewallDecision(
                allowed=True,
                action="ALLOW",
                risk=risk,
                reason="只读安全操作，允许执行"
            )

        # 3. WRITE 操作 (INSERT, UPDATE, DELETE)
        if risk.risk_level == RiskLevel.WRITE:
            if not self.policy.allow_write:
                return FirewallDecision(
                    allowed=False,
                    action="DENY",
                    risk=risk,
                    reason="当前安全策略已禁用数据写入变更 (AGENT_ALLOW_WRITE=false)。"
                )
            if self.policy.require_approval_for_write:
                req = self.approval_mgr.create_request(task_id, session_id, sql, risk.risk_level, risk.statement_type, risk.reason)
                return FirewallDecision(
                    allowed=False,
                    action="REQUIRE_APPROVAL",
                    risk=risk,
                    reason="写操作需要人工管理员审批授权。",
                    approval_request=req
                )
            return FirewallDecision(
                allowed=True,
                action="ALLOW",
                risk=risk,
                reason="写操作策略允许，放行执行"
            )

        # 4. ADMIN 操作 (CREATE INDEX, CREATE TABLE, ALTER TABLE)
        if risk.risk_level == RiskLevel.ADMIN:
            if self.policy.require_approval_for_admin:
                req = self.approval_mgr.create_request(task_id, session_id, sql, risk.risk_level, risk.statement_type, risk.reason)
                return FirewallDecision(
                    allowed=False,
                    action="REQUIRE_APPROVAL",
                    risk=risk,
                    reason=f"数据库结构变更/运维操作 ({risk.statement_type}) 触发安全审批拦截，请人工审核。",
                    approval_request=req
                )
            elif not self.policy.allow_ddl:
                return FirewallDecision(
                    allowed=False,
                    action="DENY",
                    risk=risk,
                    reason="当前安全策略已禁用 DDL/运维操作 (AGENT_ALLOW_DDL=false)。"
                )
            return FirewallDecision(
                allowed=True,
                action="ALLOW",
                risk=risk,
                reason="管理员运维操作已通过策略授权"
            )

        return FirewallDecision(
            allowed=False,
            action="DENY",
            risk=risk,
            reason="未知风险级别，默认拦截。"
        )
