# agent/agents/supervisor.py
import json
from typing import Dict, Any, Optional
from agent.models.base import BaseModelClient, ChatMessage, ModelTier
from agent.prompts import load_prompt


class SupervisorAgent:
    """
    Supervisor Agent
    负责全局意图识别 (Intent Classification) 与任务分派，不直接执行 SQL。
    """

    def __init__(self, model_client: BaseModelClient):
        self.model_client = model_client
        self.prompt_template = load_prompt("router.md")

    def route(self, user_query: str, conversation_context: str = "") -> Dict[str, Any]:
        prompt = self.prompt_template
        if conversation_context and conversation_context != "无前序对话上下文":
            prompt = f"{prompt}\n\n## 近期多轮对话上下文\n{conversation_context}"
        messages = [
            ChatMessage(role="system", content=prompt),
            ChatMessage(role="user", content=user_query)
        ]
        resp = self.model_client.chat(messages, tier=ModelTier.FAST, json_mode=True)
        if resp.parsed_json and "intent" in resp.parsed_json:
            return resp.parsed_json
        
        # 兜底解析
        try:
            data = json.loads(resp.content)
            return data
        except Exception:
            return {
                "intent": "query",
                "confidence": 0.8,
                "reason": "解析异常，默认降级为 query 意图"
            }
