# agent/hooks/base.py
from abc import ABC
from typing import Dict, Any, List, Optional


class BaseHook(ABC):
    def before_agent(self, task_id: str, query: str) -> None:
        pass

    def after_agent(self, task_id: str, final_answer: str, latency_ms: float) -> None:
        pass

    def before_sql(self, task_id: str, sql: str) -> None:
        pass

    def after_sql(self, task_id: str, sql: str, success: bool, latency_ms: float) -> None:
        pass

    def on_error(self, task_id: str, error: str) -> None:
        pass

    def on_retry(self, task_id: str, retry_count: int, failed_sql: str, corrected_sql: str) -> None:
        pass

    def on_approval(self, task_id: str, request_id: str, sql: str, status: str) -> None:
        pass


class HookManager:
    """
    全生命周期 Hook 管理中心
    """

    def __init__(self):
        self._hooks: List[BaseHook] = []

    def register(self, hook: BaseHook):
        self._hooks.append(hook)

    def trigger_before_agent(self, task_id: str, query: str):
        for h in self._hooks:
            h.before_agent(task_id, query)

    def trigger_after_agent(self, task_id: str, final_answer: str, latency_ms: float):
        for h in self._hooks:
            h.after_agent(task_id, final_answer, latency_ms)

    def trigger_before_sql(self, task_id: str, sql: str):
        for h in self._hooks:
            h.before_sql(task_id, sql)

    def trigger_after_sql(self, task_id: str, sql: str, success: bool, latency_ms: float):
        for h in self._hooks:
            h.after_sql(task_id, sql, success, latency_ms)

    def trigger_on_error(self, task_id: str, error: str):
        for h in self._hooks:
            h.on_error(task_id, error)

    def trigger_on_retry(self, task_id: str, retry_count: int, failed_sql: str, corrected_sql: str):
        for h in self._hooks:
            h.on_retry(task_id, retry_count, failed_sql, corrected_sql)

    def trigger_on_approval(self, task_id: str, request_id: str, sql: str, status: str):
        for h in self._hooks:
            h.on_approval(task_id, request_id, sql, status)
