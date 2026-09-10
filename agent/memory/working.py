# agent/memory/working.py
from typing import Dict, Any, List, Optional
from agent.memory.base import BaseMemory, MemoryItem


class WorkingMemory(BaseMemory):
    """
    工作记忆 (Working Memory)
    保存单个请求/任务运行期间的临时上下文（当前任务目标、当前生成的 SQL、最后一次编译错误、工具调用链）
    任务生命周期结束后主动释放或归档。
    """

    def __init__(self):
        self._store: Dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    def set(self, key: str, value: Any, metadata: Optional[Dict[str, Any]] = None) -> None:
        self._store[key] = value

    def update(self, mapping: Dict[str, Any]) -> None:
        self._store.update(mapping)

    def clear(self) -> None:
        self._store.clear()

    def snapshot(self) -> Dict[str, Any]:
        return dict(self._store)
