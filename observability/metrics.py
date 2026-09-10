# observability/metrics.py
import threading
import time
from typing import Dict, Any, List


class MetricsCollector:
    """
    CortexDB 原生可观测性度量收集器
    线程安全原子计数，支持 Prometheus 标准格式与 JSON 格式导出
    """

    def __init__(self):
        self._lock = threading.Lock()

        # Agent 指标
        self.agent_requests_total = 0
        self.agent_success_total = 0
        self.agent_failure_total = 0
        self.agent_retry_total = 0
        self.agent_latencies: List[float] = []

        # LLM 指标
        self.llm_requests_total = 0
        self.llm_input_tokens = 0
        self.llm_output_tokens = 0
        self.llm_errors = 0
        self.llm_latencies: List[float] = []

        # Tool 指标
        self.tool_calls_total = 0
        self.tool_failure_total = 0
        self.tool_latencies: List[float] = []

    def record_agent_request(self, success: bool, latency_ms: float, retries: int = 0):
        with self._lock:
            self.agent_requests_total += 1
            if success:
                self.agent_success_total += 1
            else:
                self.agent_failure_total += 1
            self.agent_retry_total += retries
            self.agent_latencies.append(latency_ms)
            if len(self.agent_latencies) > 500:
                self.agent_latencies.pop(0)

    def record_llm_call(self, input_tokens: int, output_tokens: int, latency_ms: float, error: bool = False):
        with self._lock:
            self.llm_requests_total += 1
            self.llm_input_tokens += input_tokens
            self.llm_output_tokens += output_tokens
            if error:
                self.llm_errors += 1
            self.llm_latencies.append(latency_ms)
            if len(self.llm_latencies) > 500:
                self.llm_latencies.pop(0)

    def record_tool_call(self, tool_name: str, latency_ms: float, success: bool = True):
        with self._lock:
            self.tool_calls_total += 1
            if not success:
                self.tool_failure_total += 1
            self.tool_latencies.append(latency_ms)
            if len(self.tool_latencies) > 500:
                self.tool_latencies.pop(0)

    def get_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            avg_agent_lat = sum(self.agent_latencies) / len(self.agent_latencies) if self.agent_latencies else 0.0
            avg_llm_lat = sum(self.llm_latencies) / len(self.llm_latencies) if self.llm_latencies else 0.0
            avg_tool_lat = sum(self.tool_latencies) / len(self.tool_latencies) if self.tool_latencies else 0.0

            return {
                "agent": {
                    "requests_total": self.agent_requests_total,
                    "success_total": self.agent_success_total,
                    "failure_total": self.agent_failure_total,
                    "retry_total": self.agent_retry_total,
                    "avg_latency_ms": round(avg_agent_lat, 2)
                },
                "llm": {
                    "requests_total": self.llm_requests_total,
                    "input_tokens_total": self.llm_input_tokens,
                    "output_tokens_total": self.llm_output_tokens,
                    "errors_total": self.llm_errors,
                    "avg_latency_ms": round(avg_llm_lat, 2)
                },
                "tool": {
                    "calls_total": self.tool_calls_total,
                    "failure_total": self.tool_failure_total,
                    "avg_latency_ms": round(avg_tool_lat, 2)
                }
            }


_global_metrics = MetricsCollector()


def get_metrics_collector() -> MetricsCollector:
    return _global_metrics
