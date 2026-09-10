# agent/middleware/rate_limit.py
import time
from typing import Optional, Dict, Any, List
from agent.middleware.base import BaseMiddleware, MiddlewareContext


class RateLimitMiddleware(BaseMiddleware):
    """
    滑动窗口频控中间件 (Rate Limiter)
    防止恶意高频并发打垮 Agent 与底层 BufferPool
    """

    def __init__(self, max_requests_per_minute: int = 60):
        self.max_requests = max_requests_per_minute
        self._user_windows: Dict[str, List[float]] = {}

    def process_request(self, ctx: MiddlewareContext) -> Optional[Dict[str, Any]]:
        now = time.time()
        key = ctx.user_id or ctx.session_id or "global"
        timestamps = self._user_windows.get(key, [])

        # 清除一分钟前的时间戳
        valid_ts = [t for t in timestamps if now - t < 60.0]
        if len(valid_ts) >= self.max_requests:
            return {
                "success": False,
                "error": "RATE_LIMIT_EXCEEDED",
                "message": f"请求过于频繁，触发限流保护 ({self.max_requests}次/分钟)，请稍后重试。"
            }

        valid_ts.append(now)
        self._user_windows[key] = valid_ts
        return None

    def process_response(self, ctx: MiddlewareContext, response: Any) -> Any:
        return response
