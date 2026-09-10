# agent/runtime/context.py
import uuid
from contextvars import ContextVar
from typing import Optional
from pydantic import BaseModel, Field

_current_trace_id: ContextVar[str] = ContextVar("current_trace_id", default="")
_current_session_id: ContextVar[str] = ContextVar("current_session_id", default="")
_current_user_id: ContextVar[str] = ContextVar("current_user_id", default="default_user")


class RequestContext(BaseModel):
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = Field(default="default_session")
    user_id: str = Field(default="default_user")

    def bind(self):
        _current_trace_id.set(self.trace_id)
        _current_session_id.set(self.session_id)
        _current_user_id.set(self.user_id)


def get_current_trace_id() -> str:
    tid = _current_trace_id.get()
    return tid if tid else str(uuid.uuid4())


def get_current_session_id() -> str:
    return _current_session_id.get() or "default_session"


def get_current_user_id() -> str:
    return _current_user_id.get() or "default_user"


def set_current_context(ctx: RequestContext):
    ctx.bind()

