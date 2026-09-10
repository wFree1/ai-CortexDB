# agent/memory/schema.py
import time
from typing import Dict, Any, List, Optional
from agent.memory.base import BaseMemory


class SchemaMemory(BaseMemory):
    """
    Schema 结构记忆 (Schema Memory)
    高效缓存数据库表、列、主键、外键元数据。在执行 DDL 或检测到 Catalog 版本变更时自动失效刷新。
    """

    def __init__(self, ttl_seconds: float = 300.0):
        self.ttl = ttl_seconds
        self._cache: Dict[str, Any] = {}
        self._last_updated: float = 0.0

    def is_expired(self) -> bool:
        return (time.time() - self._last_updated) > self.ttl

    def get(self, key: str = "summary") -> Optional[Any]:
        if self.is_expired():
            return None
        return self._cache.get(key)

    def set(self, key: str, value: Any, metadata: Optional[Dict[str, Any]] = None) -> None:
        self._cache[key] = value
        self._last_updated = time.time()

    def invalidate(self) -> None:
        self._cache.clear()
        self._last_updated = 0.0

    def clear(self) -> None:
        self.invalidate()
