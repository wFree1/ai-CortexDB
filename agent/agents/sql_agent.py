# agent/agents/sql_agent.py
import json
from typing import Dict, Any, Optional
from agent.models.base import BaseModelClient, ChatMessage, ModelTier
from agent.prompts import load_prompt


class SQLAgent:
    """
    SQL Agent
    职责：结合用户自然语言诉求、检索出的精简 Schema 与历史记忆，
    生成高度符合 DataSphere 数据库内核方言的 SQL。
    """

    def __init__(self, model_client: BaseModelClient):
        self.model_client = model_client
        self.prompt_template = load_prompt("sql_generator.md")

    def generate(
        self,
        user_query: str,
        schema_context: str,
        memory_context: str = ""
    ) -> Dict[str, Any]:
        filled_prompt = self.prompt_template.replace(
            "{user_query}", user_query
        ).replace(
            "{schema_context}", schema_context
        ).replace(
            "{memory_context}", memory_context or "暂无历史参考"
        )

        messages = [
            ChatMessage(role="system", content=filled_prompt),
            ChatMessage(role="user", content=user_query)
        ]

        resp = self.model_client.chat(messages, tier=ModelTier.MEDIUM, json_mode=True)
        if resp.parsed_json and "sql" in resp.parsed_json:
            return resp.parsed_json

        # 兜底字符串清洗
        sql_str = resp.content.strip()
        if "```" in sql_str:
            lines = sql_str.splitlines()
            code_lines = [l for l in lines if not l.startswith("```")]
            sql_str = "\n".join(code_lines).strip()

        return {
            "sql": sql_str,
            "explanation": "模型生成的 SQL 查询"
        }
