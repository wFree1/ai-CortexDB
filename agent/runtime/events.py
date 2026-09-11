# agent/runtime/events.py
import time
import json
import asyncio
from enum import Enum
from typing import Dict, Any, List, Callable, Optional
from pydantic import BaseModel, Field


class EventType(str, Enum):
    AGENT_STARTED = "agent.started"
    INTENT_DETECTED = "intent.detected"
    MEMORY_RETRIEVED = "memory.retrieved"
    SCHEMA_RETRIEVED = "schema.retrieved"
    SQL_GENERATED = "sql.generated"
    SQL_VALIDATED = "sql.validated"
    SQL_CORRECTED = "sql.corrected"
    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"
    APPROVAL_REQUIRED = "approval.required"
    APPROVAL_RESOLVED = "approval.resolved"
    CLARIFICATION_REQUIRED = "clarification.required"
    SQL_EXECUTED = "sql.executed"
    ANALYSIS_COMPLETED = "analysis.completed"
    AGENT_COMPLETED = "agent.completed"
    AGENT_ERROR = "agent.error"


class AgentEvent(BaseModel):
    event: EventType
    task_id: str
    trace_id: Optional[str] = None
    session_id: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)
    data: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event": self.event.value,
            "task_id": self.task_id,
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "data": self.data
        }

    def to_sse(self) -> str:
        return f"event: {self.event.value}\ndata: {json.dumps(self.to_dict(), ensure_ascii=False)}\n\n"


class EventBus:
    """全局异步事件总线，用于推流、可观测性监控与前端实时展示"""
    def __init__(self):
        self._listeners: List[Callable[[AgentEvent], Any]] = []
        self._async_queues: Dict[str, List[asyncio.Queue]] = {}

    def subscribe(self, callback: Callable[[AgentEvent], Any]):
        self._listeners.append(callback)

    def unsubscribe(self, callback: Callable[[AgentEvent], Any]):
        if callback in self._listeners:
            self._listeners.remove(callback)

    def publish(self, event: AgentEvent):
        # 同步回调
        for cb in self._listeners:
            try:
                cb(event)
            except Exception:
                pass

        # 异步队列推送
        if event.task_id in self._async_queues:
            for q in self._async_queues[event.task_id]:
                try:
                    q.put_nowait(event)
                except Exception:
                    pass

    def publish_sync(
        self,
        event_type: EventType,
        task_id: str,
        data: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
        session_id: Optional[str] = None
    ):
        evt = AgentEvent(
            event=event_type,
            task_id=task_id,
            trace_id=trace_id,
            session_id=session_id,
            data=data or {}
        )
        self.publish(evt)

    def register_task_queue(self, task_id: str) -> asyncio.Queue:
        q = asyncio.Queue()
        self._async_queues.setdefault(task_id, []).append(q)
        return q

    def unregister_task_queue(self, task_id: str, queue: asyncio.Queue):
        if task_id in self._async_queues:
            if queue in self._async_queues[task_id]:
                self._async_queues[task_id].remove(queue)
            if not self._async_queues[task_id]:
                del self._async_queues[task_id]


_global_event_bus = EventBus()


def get_event_bus() -> EventBus:
    return _global_event_bus
