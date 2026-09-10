# agent/models/base.py
from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class ModelTier(str, Enum):
    FAST = "FAST"          # 快速轻量模型：意图路由、SQL纠错、简单总结
    MEDIUM = "MEDIUM"      # 通用标准模型：SQL 生成、复杂分析
    LARGE = "LARGE"        # 高智商模型：深度 DBA 性能调优、复杂规划


class ChatMessage(BaseModel):
    role: str              # system, user, assistant, tool
    content: str
    name: Optional[str] = None


class ModelResponse(BaseModel):
    content: str
    parsed_json: Optional[Dict[str, Any]] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model_name: str = "unknown"
    latency_ms: float = 0.0


class BaseModelClient(ABC):
    @abstractmethod
    def chat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.0,
        tier: ModelTier = ModelTier.MEDIUM,
        json_mode: bool = False
    ) -> ModelResponse:
        pass

    @abstractmethod
    async def achat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.0,
        tier: ModelTier = ModelTier.MEDIUM,
        json_mode: bool = False
    ) -> ModelResponse:
        pass
