# agent/models/router.py
import logging
from typing import List, Dict, Any, Optional
from agent.models.base import BaseModelClient, ChatMessage, ModelResponse, ModelTier
from agent.models.openai import OpenAIModelClient
from agent.models.fallback import FallbackModelClient
from agent.config import AgentConfig, get_config

logger = logging.getLogger("cortex.model_router")


class ModelRouter(BaseModelClient):
    """
    统一模型路由分层中心
    支持分层调度 (FAST / MEDIUM / LARGE) 与零配置离线兜底 (Offline Fallback)
    """

    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or get_config()
        self.fallback_client = FallbackModelClient()
        self.primary_client: Optional[BaseModelClient] = None

        if self.config.openai_api_key and self.config.openai_api_key.strip():
            try:
                self.primary_client = OpenAIModelClient(self.config)
                logger.info(f"Initialized OpenAI model client with model={self.config.model_name}")
            except Exception as e:
                logger.warning(f"Failed to initialize primary model client: {e}. Falling back to heuristic engine.")
                self.primary_client = None
        else:
            logger.info("No OPENAI_API_KEY detected. Running in Database-Native Heuristic Fallback mode.")

    def chat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.0,
        tier: ModelTier = ModelTier.MEDIUM,
        json_mode: bool = False
    ) -> ModelResponse:
        if self.primary_client is not None:
            try:
                return self.primary_client.chat(messages, temperature=temperature, tier=tier, json_mode=json_mode)
            except Exception as e:
                logger.warning(f"Primary model client failed ({e}). Gracefully degrading to heuristic fallback.")
                return self.fallback_client.chat(messages, temperature=temperature, tier=tier, json_mode=json_mode)
        return self.fallback_client.chat(messages, temperature=temperature, tier=tier, json_mode=json_mode)

    async def achat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.0,
        tier: ModelTier = ModelTier.MEDIUM,
        json_mode: bool = False
    ) -> ModelResponse:
        if self.primary_client is not None:
            try:
                return await self.primary_client.achat(messages, temperature=temperature, tier=tier, json_mode=json_mode)
            except Exception as e:
                logger.warning(f"Primary model client async failed ({e}). Gracefully degrading to heuristic fallback.")
                return await self.fallback_client.achat(messages, temperature=temperature, tier=tier, json_mode=json_mode)
        return await self.fallback_client.achat(messages, temperature=temperature, tier=tier, json_mode=json_mode)
