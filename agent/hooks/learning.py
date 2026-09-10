# agent/hooks/learning.py
from agent.hooks.base import BaseHook
from agent.memory.manager import MemoryManager


class LearningHook(BaseHook):
    """
    自学习 Hook (Experience Learning Hook)
    在 SQL 成功执行或自愈纠正完成后，将实战经验反哺沉淀至 Episodic Memory
    """

    def __init__(self, memory_mgr: MemoryManager):
        self.memory_mgr = memory_mgr

    def on_retry(self, task_id: str, retry_count: int, failed_sql: str, corrected_sql: str) -> None:
        # 记录自愈修复经验
        self.memory_mgr.record_success_experience(
            query=f"Auto-Heal Recovery [Retry {retry_count}]",
            sql=corrected_sql,
            error=f"Initial SQL failed: {failed_sql}",
            correction=f"Corrected to: {corrected_sql}"
        )
