# agent/tools/sql.py
import json
from langchain_core.tools import tool
from agent.tools.base import ToolSpec, RiskLevel
from agent.runtime.adapter import CortexDBAdapter
from agent.config import get_config

SQL_TOOL_SPEC = ToolSpec(
    name="cortex_sql_execute",
    description="在 DataSphere 物理数据库上执行已校验的 SQL 语句，返回真实数据结果集或受影响行数。",
    risk_level=RiskLevel.WRITE,
    permissions=["sql.execute"],
    timeout=30.0
)


def get_sql_tool(adapter: CortexDBAdapter):
    @tool(SQL_TOOL_SPEC.name, description=SQL_TOOL_SPEC.description)
    def cortex_sql_execute(sql: str) -> str:
        """
        物理执行 SQL 语句。
        :param sql: 待执行的 SQL 语句。
        """
        cfg = get_config()
        res = adapter.execute(sql)
        if not res["success"]:
            return json.dumps({
                "success": False,
                "error": res["error"],
                "error_type": res["error_type"],
                "sql": res["sql"]
            }, ensure_ascii=False)

        data = res["data"]
        total_rows = len(data)
        truncated = False
        if total_rows > cfg.max_context_rows:
            data = data[:cfg.max_context_rows]
            truncated = True

        return json.dumps({
            "success": True,
            "sql": res["sql"],
            "row_count": total_rows,
            "returned_rows": len(data),
            "truncated": truncated,
            "columns": res["columns"],
            "data": data,
            "latency_ms": res["latency_ms"],
            "message": res["message"]
        }, ensure_ascii=False)

    return cortex_sql_execute
