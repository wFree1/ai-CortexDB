# agent/tools/registry.py
from typing import Dict, List, Optional, Any
from agent.tools.base import ToolSpec, RiskLevel
from agent.runtime.adapter import CortexDBAdapter

from agent.tools.schema import get_schema_tool, SCHEMA_TOOL_SPEC
from agent.tools.compiler import get_compiler_tool, COMPILER_TOOL_SPEC
from agent.tools.sql import get_sql_tool, SQL_TOOL_SPEC
from agent.tools.explain import get_explain_tool, EXPLAIN_TOOL_SPEC
from agent.tools.catalog import get_catalog_tool, CATALOG_TOOL_SPEC
from agent.tools.metrics import get_metrics_tool, METRICS_TOOL_SPEC
from agent.tools.index import get_index_advisor_tool, INDEX_ADVISOR_TOOL_SPEC
from agent.tools.diagnostics import get_diagnostics_tool, DIAGNOSTICS_TOOL_SPEC


class ToolRegistry:
    """
    CortexDB Tool 注册中心
    管理所有与底层数据库交互的 Agent Tools，附带权限与风险元数据
    """

    def __init__(self):
        self._tools: Dict[str, Any] = {}
        self._specs: Dict[str, ToolSpec] = {}

    def register(self, tool_func: Any, spec: ToolSpec):
        self._tools[spec.name] = tool_func
        self._specs[spec.name] = spec

    def get(self, name: str) -> Optional[Any]:
        return self._tools.get(name)

    def get_spec(self, name: str) -> Optional[ToolSpec]:
        return self._specs.get(name)

    def list_tools(self) -> List[Any]:
        return list(self._tools.values())

    def list_specs(self) -> List[ToolSpec]:
        return list(self._specs.values())

    def get_tools_for_agent(self, agent_role: str) -> List[Any]:
        """按 Agent 角色精细分配工具"""
        if agent_role in ("sql", "recovery"):
            names = ["cortex_schema", "cortex_sql_compile", "cortex_sql_execute", "cortex_explain"]
        elif agent_role in ("dba", "optimizer"):
            names = ["cortex_schema", "cortex_explain", "cortex_catalog", "cortex_metrics", "cortex_index_advisor", "cortex_diagnostics"]
        elif agent_role == "analyst":
            names = ["cortex_schema", "cortex_sql_execute", "cortex_metrics"]
        else:
            names = list(self._tools.keys())
        return [self._tools[n] for n in names if n in self._tools]


def create_default_registry(adapter: CortexDBAdapter) -> ToolRegistry:
    """构建包含所有 8 个核心工具的完整注册中心"""
    registry = ToolRegistry()

    # 1. Schema
    registry.register(get_schema_tool(adapter), SCHEMA_TOOL_SPEC)

    # 2. Compile Check
    registry.register(get_compiler_tool(adapter), COMPILER_TOOL_SPEC)

    # 3. SQL Execute
    registry.register(get_sql_tool(adapter), SQL_TOOL_SPEC)

    # 4. Explain
    registry.register(get_explain_tool(adapter), EXPLAIN_TOOL_SPEC)

    # 5. Catalog
    registry.register(get_catalog_tool(adapter), CATALOG_TOOL_SPEC)

    # 6. Metrics
    registry.register(get_metrics_tool(adapter), METRICS_TOOL_SPEC)

    # 7. Index Advisor
    registry.register(get_index_advisor_tool(adapter), INDEX_ADVISOR_TOOL_SPEC)

    # 8. Diagnostics
    registry.register(get_diagnostics_tool(adapter), DIAGNOSTICS_TOOL_SPEC)

    return registry
