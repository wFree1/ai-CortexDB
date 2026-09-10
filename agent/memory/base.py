# agent/memory/base.py
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class MemoryItem(BaseModel):
    key: str
    content: Any
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)


class BaseMemory(ABC):
    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        pass

    @abstractmethod
    def set(self, key: str, value: Any, metadata: Optional[Dict[str, Any]] = None) -> None:
        pass

    @abstractmethod
    def clear(self) -> None:
        pass
