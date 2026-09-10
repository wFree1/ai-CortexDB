# observability/tracing.py
import time
import uuid
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field


class Span(BaseModel):
    span_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    parent_id: Optional[str] = None
    name: str
    start_time: float = Field(default_factory=time.time)
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    status: str = "RUNNING"  # RUNNING, SUCCESS, ERROR
    attributes: Dict[str, Any] = Field(default_factory=dict)

    def finish(self, status: str = "SUCCESS", error_msg: Optional[str] = None):
        self.end_time = time.time()
        self.duration_ms = round((self.end_time - self.start_time) * 1000.0, 2)
        self.status = status
        if error_msg:
            self.attributes["error"] = error_msg


class Trace(BaseModel):
    trace_id: str = Field(default_factory=lambda: f"trace_{uuid.uuid4().hex[:12]}")
    spans: List[Span] = Field(default_factory=list)

    def start_span(self, name: str, parent_id: Optional[str] = None, attributes: Optional[Dict[str, Any]] = None) -> Span:
        span = Span(
            name=name,
            parent_id=parent_id,
            attributes=attributes or {}
        )
        self.spans.append(span)
        return span


class Tracer:
    """
    全链路调用追踪器 (Tracer)
    """

    def __init__(self):
        self._traces: Dict[str, Trace] = {}

    def get_or_create_trace(self, trace_id: Optional[str] = None) -> Trace:
        if not trace_id:
            t = Trace()
            self._traces[t.trace_id] = t
            return t
        if trace_id not in self._traces:
            self._traces[trace_id] = Trace(trace_id=trace_id)
        return self._traces[trace_id]

    def get_trace(self, trace_id: str) -> Optional[Trace]:
        return self._traces.get(trace_id)


_global_tracer = Tracer()


def get_tracer() -> Tracer:
    return _global_tracer
