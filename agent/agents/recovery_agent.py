# agent/agents/recovery_agent.py
import json
from typing import Dict, Any, Optional
from agent.models.base import BaseModelClient, ChatMessage, ModelTier
from agent.prompts import load_prompt


class RecoveryAgent:
    """
    Recovery Agent (核心自愈智能体)
    职责：当 SQL 编译预检或物理执行报错时，分析报错阶段、位置、Caret 光标行与 Hints，
    精准修正 SQL，完成闭环自愈修复。
    """

    def __init__(self, model_client: BaseModelClient):
        self.model_client = model_client
        self.prompt_template = load_prompt("sql_corrector.md")

    def recover(
        self,
        user_query: str,
        failed_sql: str,
        diagnostic_text: str,
        schema_context: str
    ) -> Dict[str, Any]:
        filled_prompt = self.prompt_template.replace(
            "{user_query}", user_query
        ).replace(
            "{failed_sql}", failed_sql
        ).replace(
            "{compiler_diagnostic}", diagnostic_text
        ).replace(
            "{schema_context}", schema_context
        )

        messages = [
            ChatMessage(role="system", content=filled_prompt),
            ChatMessage(role="user", content=f"请根据诊断报告修正 SQL:\n{failed_sql}\n诊断:\n{diagnostic_text}")
        ]

        resp = self.model_client.chat(messages, tier=ModelTier.FAST, json_mode=True)
        if resp.parsed_json and "corrected_sql" in resp.parsed_json:
            return resp.parsed_json

        # 兜底
        return {
            "corrected_sql": failed_sql,
            "root_cause": "未知错误",
            "fix_summary": "自动修复未产出有效 SQL"
        }
