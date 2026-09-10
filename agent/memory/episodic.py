# agent/memory/episodic.py
import time
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from agent.memory.base import BaseMemory


class Episode(BaseModel):
    query: str
    sql: str
    error: Optional[str] = None
    correction: Optional[str] = None
    success: bool = True
    timestamp: float = Field(default_factory=time.time)


class EpisodicMemory(BaseMemory):
    """
    情景/经验记忆 (Episodic Memory)
    记录历史执行案例、遇到的编译/运行时错误、自愈修正方案与执行效果。
    """

    def __init__(self, max_episodes: int = 100):
        self.max_episodes = max_episodes
        self._episodes: List[Episode] = []

    def record(self, query: str, sql: str, error: Optional[str] = None, correction: Optional[str] = None, success: bool = True):
        ep = Episode(
            query=query,
            sql=sql,
            error=error,
            correction=correction,
            success=success
        )
        self._episodes.append(ep)
        if len(self._episodes) > self.max_episodes:
            self._episodes.pop(0)

    def find_similar(self, query: str, limit: int = 3) -> List[Episode]:
        """按关键词重合度进行快速经验检索"""
        query_words = set(query.lower())
        scored = []
        for ep in self._episodes:
            ep_words = set(ep.query.lower())
            overlap = len(query_words & ep_words)
            if overlap > 0:
                scored.append((overlap, ep))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:limit]]

    def get(self, key: str) -> Optional[Any]:
        return self._episodes

    def set(self, key: str, value: Any, metadata: Optional[Dict[str, Any]] = None) -> None:
        if isinstance(value, Episode):
            self._episodes.append(value)

    def clear(self) -> None:
        self._episodes.clear()
