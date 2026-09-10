# agent/services/streaming.py
import asyncio
from typing import AsyncGenerator, Any
from agent.runtime.events import EventBus, EventType, AgentEvent
from agent.services.execution import ExecutionService


class StreamingService:
    """
    流式响应服务 (Server-Sent Events)
    向 Web 端与 API 实时推送 Agent 执行链路的细粒度事件
    """

    def __init__(self, execution_service: ExecutionService, event_bus: EventBus):
        self.execution_service = execution_service
        self.event_bus = event_bus

    async def stream_chat(
        self,
        query: str,
        session_id: str = "default_session",
        user_id: str = "default_user"
    ) -> AsyncGenerator[str, None]:
        # 预先生成 task_id
        import uuid
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        queue = self.event_bus.register_task_queue(task_id)

        # 在后台异步线程执行 LangGraph 同步任务
        loop = asyncio.get_event_loop()
        future = loop.run_in_executor(
            None,
            lambda: self.execution_service.run(
                query=query,
                session_id=session_id,
                user_id=user_id
            )
        )

        try:
            while not future.done() or not queue.empty():
                try:
                    event: AgentEvent = await asyncio.wait_for(queue.get(), timeout=0.2)
                    yield event.to_sse()
                except asyncio.TimeoutError:
                    continue

            # 最终结果
            res = await future
            # 补发一个最终完成包（若有）
            yield f"event: final_result\ndata: {import_json_dumps(res)}\n\n"

        finally:
            self.event_bus.unregister_task_queue(task_id, queue)


def import_json_dumps(data: Any) -> str:
    import json
    return json.dumps(data, ensure_ascii=False)
