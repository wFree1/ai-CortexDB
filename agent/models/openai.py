# agent/models/openai.py
import json
import time
from typing import List, Dict, Any, Optional
from agent.models.base import BaseModelClient, ChatMessage, ModelResponse, ModelTier
from agent.config import AgentConfig


class OpenAIModelClient(BaseModelClient):
    """
    OpenAI 兼容协议客户端 (支持 OpenAI, DeepSeek, Qwen, Ollama, vLLM 等)
    """

    def __init__(self, config: AgentConfig):
        self.config = config
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

        self.SystemMessage = SystemMessage
        self.HumanMessage = HumanMessage
        self.AIMessage = AIMessage

        # 初始化不同 Tier 的 ChatOpenAI 实例
        # 若未单独配置各 Tier 模型，默认复用主模型
        fast_model = config.router_model or config.model_name
        med_model = config.model_name
        large_model = config.dba_model or config.model_name

        self._llms = {
            ModelTier.FAST: ChatOpenAI(
                model=fast_model,
                api_key=config.openai_api_key,
                base_url=config.openai_api_base or None,
                temperature=0.0,
                timeout=config.agent_timeout
            ),
            ModelTier.MEDIUM: ChatOpenAI(
                model=med_model,
                api_key=config.openai_api_key,
                base_url=config.openai_api_base or None,
                temperature=0.0,
                timeout=config.agent_timeout
            ),
            ModelTier.LARGE: ChatOpenAI(
                model=large_model,
                api_key=config.openai_api_key,
                base_url=config.openai_api_base or None,
                temperature=0.0,
                timeout=config.agent_timeout
            )
        }

    def _convert_messages(self, messages: List[ChatMessage]):
        converted = []
        for m in messages:
            if m.role == "system":
                converted.append(self.SystemMessage(content=m.content))
            elif m.role == "assistant":
                converted.append(self.AIMessage(content=m.content))
            else:
                converted.append(self.HumanMessage(content=m.content))
        return converted

    def _parse_json_safely(self, text: str) -> Optional[Dict[str, Any]]:
        text = text.strip()
        # 处理 markdown ```json ... ``` 代码块包裹
        if text.startswith("```"):
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        try:
            return json.loads(text)
        except Exception:
            return None

    def chat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.0,
        tier: ModelTier = ModelTier.MEDIUM,
        json_mode: bool = False
    ) -> ModelResponse:
        llm = self._llms.get(tier, self._llms[ModelTier.MEDIUM])
        conv_msgs = self._convert_messages(messages)

        t0 = time.perf_counter()
        resp = llm.invoke(conv_msgs)
        latency = (time.perf_counter() - t0) * 1000.0

        content = resp.content if isinstance(resp.content, str) else str(resp.content)
        parsed = self._parse_json_safely(content) if json_mode else None

        usage = getattr(resp, "response_metadata", {}).get("token_usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        comp_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", prompt_tokens + comp_tokens)

        return ModelResponse(
            content=content,
            parsed_json=parsed,
            prompt_tokens=prompt_tokens,
            completion_tokens=comp_tokens,
            total_tokens=total_tokens,
            model_name=getattr(llm, "model_name", "openai-compatible"),
            latency_ms=latency
        )

    async def achat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.0,
        tier: ModelTier = ModelTier.MEDIUM,
        json_mode: bool = False
    ) -> ModelResponse:
        llm = self._llms.get(tier, self._llms[ModelTier.MEDIUM])
        conv_msgs = self._convert_messages(messages)

        t0 = time.perf_counter()
        resp = await llm.ainvoke(conv_msgs)
        latency = (time.perf_counter() - t0) * 1000.0

        content = resp.content if isinstance(resp.content, str) else str(resp.content)
        parsed = self._parse_json_safely(content) if json_mode else None

        usage = getattr(resp, "response_metadata", {}).get("token_usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        comp_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", prompt_tokens + comp_tokens)

        return ModelResponse(
            content=content,
            parsed_json=parsed,
            prompt_tokens=prompt_tokens,
            completion_tokens=comp_tokens,
            total_tokens=total_tokens,
            model_name=getattr(llm, "model_name", "openai-compatible"),
            latency_ms=latency
        )
