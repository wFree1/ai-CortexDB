# agent/agents/dba_agent.py
import json
from typing import Dict, Any, Optional
from agent.models.base import BaseModelClient, ChatMessage, ModelTier
from agent.prompts import load_prompt


class DBAAgent:
    """
    DBA Agent
    职责：分析 BufferPool 状态、慢查询、执行计划瓶颈，生成专业诊断与索引调优建议。
    """

    def __init__(self, model_client: BaseModelClient):
        self.model_client = model_client
        self.prompt_template = load_prompt("dba.md")

    def diagnose(
        self,
        user_query: str,
        metrics_context: str,
        explain_context: str,
        catalog_context: str,
        diagnostics_context: str
    ) -> Dict[str, Any]:
        filled_prompt = self.prompt_template.replace(
            "{user_query}", user_query
        ).replace(
            "{metrics_context}", metrics_context
        ).replace(
            "{explain_context}", explain_context
        ).replace(
            "{catalog_context}", catalog_context
        ).replace(
            "{diagnostics_context}", diagnostics_context
        )

        messages = [
            ChatMessage(role="system", content=filled_prompt),
            ChatMessage(role="user", content=user_query)
        ]

        resp = self.model_client.chat(messages, tier=ModelTier.LARGE, json_mode=True)
        if resp.parsed_json and "diagnosis_summary" in resp.parsed_json:
            return resp.parsed_json

        return {
            "diagnosis_summary": resp.content,
            "bottlenecks": [],
            "recommendations": [],
            "final_advice": resp.content
        }
