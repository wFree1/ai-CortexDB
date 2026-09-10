# agent/runtime/runtime.py
import time
from typing import Dict, Any, Optional
from agent.runtime.pool import get_db_pool, DatabaseSession
from agent.runtime.events import get_event_bus, AgentEvent, EventType
from agent.runtime.context import get_current_trace_id, get_current_session_id


class CortexRuntime:
    """
    CortexDB 统一运行时环境管理.
    提供高层统一调度的执行上下文、事件监控与资源调度。
    """
    def __init__(self, pool=None, event_bus=None):
        self.pool = pool or get_db_pool()
        self.event_bus = event_bus or get_event_bus()

    def get_session(self) -> DatabaseSession:
        return self.pool.acquire()

    def release_session(self, session: DatabaseSession):
        self.pool.release(session)

    def emit_event(self, event_type: EventType, task_id: str, data: Dict[str, Any]):
        event = AgentEvent(
            event=event_type,
            task_id=task_id,
            trace_id=get_current_trace_id(),
            session_id=get_current_session_id(),
            timestamp=time.time(),
            data=data
        )
        self.event_bus.publish(event)


_global_runtime: Optional[CortexRuntime] = None


def get_runtime() -> CortexRuntime:
    global _global_runtime
    if _global_runtime is None:
        _global_runtime = CortexRuntime()
    return _global_runtime
