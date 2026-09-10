# agent/middleware/sql_guard.py
from typing import Optional, Dict, Any
from agent.middleware.base import BaseMiddleware, MiddlewareContext
from agent.security.firewall import SQLFirewall, FirewallDecision


class SQLGuardMiddleware(BaseMiddleware):
    """
    SQL 门禁中间件 (SQL Guard)
    在任何 SQL 抵达执行层之前，强制过一遍 SQL 防火墙
    """

    def __init__(self, firewall: Optional[SQLFirewall] = None):
        self.firewall = firewall or SQLFirewall()

    def process_request(self, ctx: MiddlewareContext) -> Optional[Dict[str, Any]]:
        if not ctx.sql:
            return None

        decision: FirewallDecision = self.firewall.inspect(
            ctx.sql,
            task_id=ctx.trace_id,
            session_id=ctx.session_id
        )

        if not decision.allowed:
            return {
                "success": False,
                "error": "SECURITY_FIREWALL_BLOCK",
                "action": decision.action,
                "risk_level": decision.risk.risk_level.value,
                "reason": decision.reason,
                "approval_required": decision.action == "REQUIRE_APPROVAL",
                "approval_request_id": decision.approval_request.request_id if decision.approval_request else None
            }

        return None

    def process_response(self, ctx: MiddlewareContext, response: Any) -> Any:
        return response
