# agent/services/execution.py
import time
import uuid
from typing import Dict, Any, Optional
from agent.runtime.adapter import CortexDBAdapter
from agent.runtime.events import EventBus, get_event_bus
from agent.models.router import ModelRouter
from agent.memory.manager import MemoryManager
from agent.security.firewall import SQLFirewall
from agent.graph.graph import build_cortex_graph
from agent.middleware.base import MiddlewareChain, MiddlewareContext
from agent.middleware.context import ContextMiddleware
from agent.middleware.rate_limit import RateLimitMiddleware
from agent.middleware.logging import LoggingMiddleware
from agent.hooks.base import HookManager
from agent.hooks.audit import AuditHook
from agent.hooks.learning import LearningHook
from observability.metrics import get_metrics_collector


class ExecutionService:
    """
    Agent 统一核心执行服务
    装配完整的 Middleware 流水线、LangGraph 状态图、六层记忆、生命周期 Hooks 与可观测性统计
    """

    def __init__(
        self,
        adapter: Optional[CortexDBAdapter] = None,
        model_client: Optional[ModelRouter] = None,
        memory_mgr: Optional[MemoryManager] = None,
        event_bus: Optional[EventBus] = None,
        firewall: Optional[SQLFirewall] = None
    ):
        self.adapter = adapter or CortexDBAdapter()
        self.model_client = model_client or ModelRouter()
        self.memory_mgr = memory_mgr or MemoryManager()
        self.event_bus = event_bus or get_event_bus()
        self.firewall = firewall or SQLFirewall()
        self.metrics = get_metrics_collector()

        # 初始化 Hooks
        self.hooks = HookManager()
        self.audit_hook = AuditHook()
        self.learning_hook = LearningHook(self.memory_mgr)
        self.hooks.register(self.audit_hook)
        self.hooks.register(self.learning_hook)

        # 初始化中间件链
        self.middleware_chain = MiddlewareChain()
        self.middleware_chain.add(ContextMiddleware())
        self.middleware_chain.add(RateLimitMiddleware(max_requests_per_minute=120))
        self.middleware_chain.add(LoggingMiddleware())

        # 编译 LangGraph
        self.graph = build_cortex_graph(
            self.adapter,
            self.model_client,
            self.memory_mgr,
            self.event_bus,
            self.firewall
        )

    def run(
        self,
        query: str,
        session_id: str = "default_session",
        user_id: str = "default_user",
        user_role: str = "developer"
    ) -> Dict[str, Any]:
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        ctx = MiddlewareContext(
            trace_id=task_id,
            session_id=session_id,
            user_id=user_id,
            user_role=user_role
        )

        def _handler(c: MiddlewareContext) -> Dict[str, Any]:
            t0 = time.perf_counter()
            self.hooks.trigger_before_agent(task_id, query)

            # 更新用户会话历史
            self.memory_mgr.conversation.add_message(session_id, "user", query)

            history_messages = self.memory_mgr.conversation.get_messages(session_id)
            initial_state = {
                "request_id": task_id,
                "session_id": session_id,
                "messages": history_messages if history_messages else [{"role": "user", "content": query}]
            }

            try:
                final_state = self.graph.invoke(initial_state)
                latency = (time.perf_counter() - t0) * 1000.0

                answer = final_state.get("final_answer", "")
                sql = final_state.get("generated_sql")
                success = True
                if final_state.get("execution_result"):
                    success = final_state["execution_result"].get("success", True)
                elif final_state.get("approval_required"):
                    success = True
                elif final_state.get("validation") and not final_state["validation"].get("valid", True):
                    success = False

                self.hooks.trigger_after_agent(task_id, answer, latency)
                if sql:
                    self.hooks.trigger_after_sql(task_id, sql, success, latency)
                self.metrics.record_agent_request(success, latency, final_state.get("retry_count", 0))

                # 更新助手回答历史
                if answer:
                    self.memory_mgr.conversation.add_message(session_id, "assistant", answer)

                return {
                    "success": success,
                    "task_id": task_id,
                    "session_id": session_id,
                    "query": query,
                    "intent": final_state.get("intent"),
                    "generated_sql": sql,
                    "validation": final_state.get("validation"),
                    "explain": final_state.get("explain"),
                    "needs_clarification": final_state.get("needs_clarification", False),
                    "clarification_question": final_state.get("clarification_question"),
                    "approval_required": final_state.get("approval_required", False),
                    "approval_request_id": final_state.get("approval_request_id"),
                    "risk_level": final_state.get("risk_level"),
                    "retry_count": final_state.get("retry_count", 0),
                    "execution_result": final_state.get("execution_result"),
                    "optimization_comparison": final_state.get("optimization_comparison"),
                    "answer": answer,
                    "final_answer": answer,
                    "latency_ms": round(latency, 2)
                }

            except Exception as e:
                latency = (time.perf_counter() - t0) * 1000.0
                self.hooks.trigger_on_error(task_id, str(e))
                self.metrics.record_agent_request(False, latency)
                return {
                    "success": False,
                    "task_id": task_id,
                    "error": str(e),
                    "answer": f"执行遇到未捕获异常: {e}"
                }

        return self.middleware_chain.execute(ctx, _handler)

    def close(self):
        if self.adapter:
            self.adapter.close()
