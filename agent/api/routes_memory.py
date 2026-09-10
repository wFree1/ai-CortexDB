# agent/api/routes_memory.py
from fastapi import APIRouter
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from agent.api.dependencies import get_services

router = APIRouter(prefix="/api/v1/memory", tags=["Memory"])


class MemoryContextRequest(BaseModel):
    query: str
    session_id: str = "default_session"


@router.post("/context")
def retrieve_memory_context(req: MemoryContextRequest) -> Dict[str, Any]:
    exec_svc, _, _ = get_services()
    return exec_svc.memory_mgr.retrieve_context(req.query, req.session_id)


@router.post("/clear")
def clear_memory(session_id: Optional[str] = None) -> Dict[str, Any]:
    exec_svc, _, _ = get_services()
    if session_id:
        exec_svc.memory_mgr.conversation.clear_session(session_id)
        return {"success": True, "message": f"Session {session_id} memory cleared"}
    exec_svc.memory_mgr.reset_working_memory()
    return {"success": True, "message": "Working memory cleared"}
