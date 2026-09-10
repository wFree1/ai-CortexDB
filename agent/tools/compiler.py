# agent/tools/compiler.py
import json
from langchain_core.tools import tool
from agent.tools.base import ToolSpec, RiskLevel
from agent.runtime.adapter import CortexDBAdapter
from agent.tools.diagnostics import DiagnosticAdapter

COMPILER_TOOL_SPEC = ToolSpec(
    name="cortex_sql_compile",
    description="对 SQL 进行编译器前置质检（词法、语法、语义分析），不触碰底层磁盘数据。用于在执行前拦截任何语法或列名错误。",
    risk_level=RiskLevel.READ,
    permissions=["sql.validate"],
    timeout=5.0
)


def get_compiler_tool(adapter: CortexDBAdapter):
    @tool(COMPILER_TOOL_SPEC.name, description=COMPILER_TOOL_SPEC.description)
    def cortex_sql_compile(sql: str) -> str:
        """
        进行内核编译预检。
        :param sql: 待校验的 SQL 语句。
        :return: JSON 字符串，包含 valid (bool), stage, error_code, error_message, hints 等诊断信息。
        """
        val_res = adapter.validate(sql)
        diag = DiagnosticAdapter.parse_error(
            val_res.get("error_message", ""),
            val_res.get("error_type"),
            val_res.get("smart_hints")
        )
        return json.dumps({
            "valid": val_res["valid"],
            "diagnostic": diag.model_dump(),
            "guidance": diag.to_correction_prompt()
        }, ensure_ascii=False)

    return cortex_sql_compile
