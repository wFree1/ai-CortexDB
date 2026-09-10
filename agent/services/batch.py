# agent/services/batch.py
import asyncio
from typing import List, Dict, Any, Optional
from agent.services.execution import ExecutionService


class BatchService:
    """
    异步批量任务规划与调度服务 (Batch Planner & Concurrency Limiter)
    例如按部门分拆执行，统计聚合，带并发流控
    """

    def __init__(self, execution_service: ExecutionService, max_concurrency: int = 5):
        self.execution_service = execution_service
        self.semaphore = asyncio.Semaphore(max_concurrency)

    async def execute_batch(self, queries: List[str], session_id: str = "batch_session") -> List[Dict[str, Any]]:
        loop = asyncio.get_event_loop()

        async def _run_single(q: str):
            async with self.semaphore:
                return await loop.run_in_executor(
                    None,
                    lambda: self.execution_service.run(query=q, session_id=session_id)
                )

        tasks = [_run_single(q) for q in queries]
        return await asyncio.gather(*tasks)
