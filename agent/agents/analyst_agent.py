# agent/agents/analyst_agent.py
from typing import Dict, Any, List, Optional
from agent.models.base import BaseModelClient, ChatMessage, ModelTier
from agent.prompts import load_prompt


class AnalystAgent:
    """
    Analyst Agent / Synthesizer
    职责：结果大集采样与保护、统计分析、自然语言汇总与 Markdown 格式化输出。
    """

    def __init__(self, model_client: BaseModelClient):
        self.model_client = model_client
        self.prompt_template = load_prompt("synthesizer.md")

    def format_table_markdown(self, columns: List[str], rows: List[List[Any]], max_rows: int = 20) -> str:
        if not columns or not rows:
            return "*(无返回数据行)*"
        
        display_rows = rows[:max_rows]
        lines = []
        # 表头
        lines.append("| " + " | ".join(str(c) for c in columns) + " |")
        lines.append("| " + " | ".join(["---"] * len(columns)) + " |")
        # 数据
        for r in display_rows:
            row_str = " | ".join(str(v) if v is not None else "NULL" for v in r)
            lines.append(f"| {row_str} |")
        
        if len(rows) > max_rows:
            lines.append(f"\n*(已截断显示前 {max_rows} 行，共 {len(rows)} 行)*")
        
        return "\n".join(lines)

    def synthesize(
        self,
        user_query: str,
        intent: str,
        final_sql: str,
        validation_status: str,
        execution_result: Optional[Dict[str, Any]],
        optimization_summary: str = ""
    ) -> str:
        exec_summary = ""
        latency = 0.0

        if execution_result:
            latency = execution_result.get("latency_ms", 0.0)
            if execution_result.get("success"):
                rows = execution_result.get("data", [])
                cols = execution_result.get("columns", [])
                sample = rows[:2] if rows else []
                exec_summary = f"执行成功，返回 {len(rows)} 行记录。涉及字段: {cols}。样本数据: {sample}"
            else:
                exec_summary = f"执行失败: {execution_result.get('error', '未知错误')}"
        else:
            exec_summary = "无需执行物理 SQL。"

        filled_prompt = self.prompt_template.replace(
            "{user_query}", user_query
        ).replace(
            "{intent}", intent
        ).replace(
            "{final_sql}", final_sql or "N/A"
        ).replace(
            "{validation_status}", validation_status
        ).replace(
            "{execution_summary}", exec_summary
        ).replace(
            "{latency_ms}", str(round(latency, 2))
        ).replace(
            "{optimization_summary}", optimization_summary or "无"
        )

        messages = [
            ChatMessage(role="system", content=filled_prompt),
            ChatMessage(role="user", content="请直接给出简明扼要的核心业务结论，不需要重复输出 SQL 语句，不使用多级大标题报告模板。")
        ]

        resp = self.model_client.chat(messages, tier=ModelTier.FAST)
        return resp.content
