# agent/middleware/timeout.py
import time
from typing import Optional, Dict, Any
from agent.middleware.base import BaseMiddleware, MiddlewareContext


class TimeoutMiddleware(BaseMiddleware):
    """
    超时监控中间件
    """

    def __init__(self, timeout_seconds: float = 300.0):
        self.timeout_seconds = timeout_seconds

    def process_request(self, ctx: MiddlewareContext) -> Optional[Dict[str, Any]]:
        # 记录超时阈值
        ctx.metadata["timeout_at"] = time.time() + self.timeout_seconds
        return None

    def process_response(self, ctx: MiddlewareContext, response: Any) -> Any:
        timeout_at = ctx.metadata.get("timeout_at")
        if timeout_at and time.time() > timeout_at:
            if isinstance(response, dict):
                response["warning"] = "Task execution exceeded target timeout deadline."
        return response
