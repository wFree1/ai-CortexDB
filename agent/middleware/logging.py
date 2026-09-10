# agent/middleware/logging.py
import logging
import time
from typing import Optional, Dict, Any
from agent.middleware.base import BaseMiddleware, MiddlewareContext

logger = logging.getLogger("cortex.middleware.logging")


class LoggingMiddleware(BaseMiddleware):
    """
    结构化日志记录中间件
    """

    def process_request(self, ctx: MiddlewareContext) -> Optional[Dict[str, Any]]:
        logger.info(f"[REQUEST-START] trace_id={ctx.trace_id} user={ctx.user_id} session={ctx.session_id}")
        return None

    def process_response(self, ctx: MiddlewareContext, response: Any) -> Any:
        duration_ms = (time.time() - ctx.start_time) * 1000.0
        success = True
        if isinstance(response, dict) and not response.get("success", True):
            success = False
        logger.info(
            f"[REQUEST-END] trace_id={ctx.trace_id} success={success} duration={round(duration_ms, 2)}ms"
        )
        return response
