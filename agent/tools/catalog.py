# agent/tools/catalog.py
import json
from langchain_core.tools import tool
from agent.tools.base import ToolSpec, RiskLevel
from agent.runtime.adapter import CortexDBAdapter

CATALOG_TOOL_SPEC = ToolSpec(
    name="cortex_catalog",
    description="获取 DataSphere 数据库完整底层 Catalog 元数据字典，包含所有表、物理列定义、类型、主键及现有系统索引。",
    risk_level=RiskLevel.READ,
    permissions=["sql.read"],
    timeout=10.0,
    retryable=True
)


def get_catalog_tool(adapter: CortexDBAdapter):
    @tool(CATALOG_TOOL_SPEC.name, description=CATALOG_TOOL_SPEC.description)
    def cortex_catalog(table_name: str = "") -> str:
        """
        获取数据库底层系统 Catalog。若指定 table_name 则只返回指定表信息。
        :param table_name: 可选表名，为空则返回所有表定义。
        """
        cat = adapter.get_catalog_dict()
        if table_name and table_name in cat:
            return json.dumps({table_name: cat[table_name]}, ensure_ascii=False, indent=2)
        return json.dumps(cat, ensure_ascii=False, indent=2)

    return cortex_catalog
