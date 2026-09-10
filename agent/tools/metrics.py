# agent/tools/metrics.py
import json
from langchain_core.tools import tool
from agent.tools.base import ToolSpec, RiskLevel
from agent.runtime.adapter import CortexDBAdapter

METRICS_TOOL_SPEC = ToolSpec(
    name="cortex_metrics",
    description="获取 DataSphere 核心存储与缓存引擎度量指标（BufferPool 命中率、Cache Hits/Misses、脏页、页面表等），供 DBA 性能诊断。",
    risk_level=RiskLevel.READ,
    permissions=["dba.metrics"],
    timeout=5.0,
    retryable=True
)


def get_metrics_tool(adapter: CortexDBAdapter):
    @tool(METRICS_TOOL_SPEC.name, description=METRICS_TOOL_SPEC.description)
    def cortex_metrics() -> str:
        """
        获取当前 DataSphere 数据库运行状态及 BufferPool 内存指标。
        """
        metrics = adapter.get_buffer_metrics()
        return json.dumps(metrics, ensure_ascii=False, indent=2)

    return cortex_metrics
