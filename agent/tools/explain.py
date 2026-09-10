# agent/tools/explain.py
import json
from langchain_core.tools import tool
from agent.tools.base import ToolSpec, RiskLevel
from agent.runtime.adapter import CortexDBAdapter

EXPLAIN_TOOL_SPEC = ToolSpec(
    name="cortex_explain",
    description="获取指定查询的优化器逻辑与物理执行计划树，用于分析全表扫描 (TableScan)、索引扫描 (IndexScan) 与关联效率。",
    risk_level=RiskLevel.READ,
    permissions=["sql.explain"],
    timeout=5.0
)


def get_explain_tool(adapter: CortexDBAdapter):
    @tool(EXPLAIN_TOOL_SPEC.name, description=EXPLAIN_TOOL_SPEC.description)
    def cortex_explain(sql: str) -> str:
        """
        生成查询执行计划。
        :param sql: SELECT 查询语句。
        """
        res = adapter.explain(sql)
        return json.dumps(res, ensure_ascii=False, indent=2)

    return cortex_explain
