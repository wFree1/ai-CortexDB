# agent/middleware/context.py
import uuid
import time
from typing import Optional, Dict, Any
from agent.middleware.base import BaseMiddleware, MiddlewareContext
from agent.runtime.context import set_current_context, RequestContext


class ContextMiddleware(BaseMiddleware):
    """
    请求上下文中间件：自动初始化或透传 trace_id、session_id、请求起止时间
    """

    def process_request(self, ctx: MiddlewareContext) -> Optional[Dict[str, Any]]:
        if not ctx.trace_id or ctx.trace_id == "default_trace":
            ctx.trace_id = f"trace_{uuid.uuid4().hex[:12]}"
        ctx.start_time = time.time()
        # 绑定到当前协程/线程 ContextVar
        req_ctx = RequestContext(
            trace_id=ctx.trace_id,
            session_id=ctx.session_id,
            user_id=ctx.user_id,
            user_role=ctx.user_role
        )
        set_current_context(req_ctx)
        return None

    def process_response(self, ctx: MiddlewareContext, response: Any) -> Any:
        duration_ms = (time.time() - ctx.start_time) * 1000.0
        if isinstance(response, dict):
            response["trace_id"] = ctx.trace_id
            response["duration_ms"] = round(duration_ms, 2)
        return response
