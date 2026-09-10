# agent/api/routes_agent.py
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from agent.api.dependencies import get_services

router = APIRouter(prefix="/api/v1/agent", tags=["Agent"])


class ChatRequest(BaseModel):
    query: str = Field(..., description="用户的自然语言诉求或需要执行的 SQL")
    session_id: str = Field(default="default_session", description="多轮对话隔离 ID")
    user_id: str = Field(default="default_user", description="操作者身份")
    user_role: str = Field(default="developer", description="操作者角色权限")


@router.post("/chat")
def chat(req: ChatRequest) -> Dict[str, Any]:
    """
    同步 Agent 交互接口
    完整经历 Context -> Memory -> Intent -> Schema -> SQL -> Guard -> Compiler -> Recovery -> Execute -> Synthesize
    """
    exec_svc, _, _ = get_services()
    result = exec_svc.run(
        query=req.query,
        session_id=req.session_id,
        user_id=req.user_id,
        user_role=req.user_role
    )
    return result


@router.post("/stream")
async def stream_chat(req: ChatRequest):
    """
    流式 SSE 交互接口
    实时输出 Agent 思考链路与内核编译/执行步骤
    """
    _, stream_svc, _ = get_services()
    return StreamingResponse(
        stream_svc.stream_chat(
            query=req.query,
            session_id=req.session_id,
            user_id=req.user_id
        ),
        media_type="text/event-stream"
    )
