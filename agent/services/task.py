# agent/services/task.py
import time
from enum import Enum
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AgentTask(BaseModel):
    task_id: str
    session_id: str
    query: str
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class TaskService:
    """
    异步任务管理中枢
    """

    def __init__(self):
        self._tasks: Dict[str, AgentTask] = {}

    def create_task(self, task_id: str, session_id: str, query: str) -> AgentTask:
        t = AgentTask(task_id=task_id, session_id=session_id, query=query, status=TaskStatus.RUNNING)
        self._tasks[task_id] = t
        return t

    def get_task(self, task_id: str) -> Optional[AgentTask]:
        return self._tasks.get(task_id)

    def complete_task(self, task_id: str, result: Dict[str, Any]):
        if task_id in self._tasks:
            t = self._tasks[task_id]
            t.status = TaskStatus.COMPLETED
            t.result = result
            t.updated_at = time.time()

    def fail_task(self, task_id: str, error: str):
        if task_id in self._tasks:
            t = self._tasks[task_id]
            t.status = TaskStatus.FAILED
            t.error = error
            t.updated_at = time.time()

    def cancel_task(self, task_id: str) -> bool:
        if task_id in self._tasks:
            t = self._tasks[task_id]
            if t.status in (TaskStatus.RUNNING, TaskStatus.WAITING_APPROVAL):
                t.status = TaskStatus.CANCELLED
                t.updated_at = time.time()
                return True
        return False

    def list_tasks(self, limit: int = 50) -> List[AgentTask]:
        return list(reversed(list(self._tasks.values())))[:limit]
