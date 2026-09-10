# agent/tools/schema.py
from typing import Optional, List
from langchain_core.tools import tool
from agent.tools.base import ToolSpec, RiskLevel
from agent.runtime.adapter import CortexDBAdapter

SCHEMA_TOOL_SPEC = ToolSpec(
    name="cortex_schema",
    description="获取数据库的表结构、列定义、数据类型、主键与外键关联关系。可传入特定表名以节省上下文。",
    risk_level=RiskLevel.READ,
    permissions=["sql.read"],
    timeout=5.0
)


def get_schema_tool(adapter: CortexDBAdapter):
    @tool(SCHEMA_TOOL_SPEC.name, description=SCHEMA_TOOL_SPEC.description)
    def cortex_schema(tables: Optional[List[str]] = None) -> str:
        """
        获取数据库表结构信息。
        :param tables: 可选的表名列表（例如 ['employees', 'departments']）。若不传则返回所有表的紧凑描述。
        """
        return adapter.get_schema_summary(target_tables=tables)

    return cortex_schema
