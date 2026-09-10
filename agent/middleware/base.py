# agent/middleware/base.py
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Callable
from pydantic import BaseModel, Field


class MiddlewareContext(BaseModel):
    trace_id: str = "default_trace"
    session_id: str = "default_session"
    user_id: str = "default_user"
    user_role: str = "developer"
    start_time: float = Field(default_factory=time.time)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    sql: Optional[str] = None
    action: Optional[str] = None
    error: Optional[str] = None


class BaseMiddleware(ABC):
    @abstractmethod
    def process_request(self, ctx: MiddlewareContext) -> Optional[Dict[str, Any]]:
        """
        前置中间件处理。若返回字典，则直接短路拦截；若返回 None，则继续放行执行。
        """
        pass

    @abstractmethod
    def process_response(self, ctx: MiddlewareContext, response: Any) -> Any:
        """
        后置中间件处理，可对响应体进行脱敏、统计或元数据注入。
        """
        pass


class MiddlewareChain:
    """
    洋葱模型 / 流水线中间件链
    """

    def __init__(self):
        self._middlewares: List[BaseMiddleware] = []

    def add(self, middleware: BaseMiddleware) -> "MiddlewareChain":
        self._middlewares.append(middleware)
        return self

    def execute(self, ctx: MiddlewareContext, handler: Callable[[MiddlewareContext], Any]) -> Any:
        # 1. 顺序执行前置处理
        for mw in self._middlewares:
            blocked_result = mw.process_request(ctx)
            if blocked_result is not None:
                return blocked_result

        # 2. 执行核心处理器
        res = handler(ctx)

        # 3. 逆序执行后置处理
        for mw in reversed(self._middlewares):
            res = mw.process_response(ctx, res)

        return res
