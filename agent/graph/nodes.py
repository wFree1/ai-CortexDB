# agent/graph/nodes.py
import json
import time
from typing import Dict, Any, Optional

from agent.graph.state import CortexAgentState
from agent.runtime.adapter import CortexDBAdapter
from agent.runtime.events import EventBus, EventType
from agent.models.base import BaseModelClient
from agent.memory.manager import MemoryManager
from agent.security.firewall import SQLFirewall
from agent.tools.diagnostics import DiagnosticAdapter
from agent.agents.supervisor import SupervisorAgent
from agent.agents.sql_agent import SQLAgent
from agent.agents.recovery_agent import RecoveryAgent
from agent.agents.dba_agent import DBAAgent
from agent.agents.optimizer_agent import OptimizerAgent
from agent.agents.analyst_agent import AnalystAgent


class GraphNodes:
    """
    LangGraph 所有执行节点的实现与状态转移逻辑
    """

    def __init__(
        self,
        adapter: CortexDBAdapter,
        model_client: BaseModelClient,
        memory_mgr: MemoryManager,
        event_bus: EventBus,
        firewall: SQLFirewall
    ):
        self.adapter = adapter
        self.model_client = model_client
        self.memory_mgr = memory_mgr
        self.event_bus = event_bus
        self.firewall = firewall

        # 实例化专属 Agents
        self.supervisor = SupervisorAgent(model_client)
        self.sql_agent = SQLAgent(model_client)
        self.recovery_agent = RecoveryAgent(model_client)
        self.dba_agent = DBAAgent(model_client)
        self.optimizer_agent = OptimizerAgent(adapter)
        self.analyst_agent = AnalystAgent(model_client)

    def _get_user_query(self, state: CortexAgentState) -> str:
        messages = state.get("messages", [])
        for m in reversed(messages):
            if m.get("role") == "user":
                return m.get("content", "")
        return ""

    # 1. context_node
    def context_node(self, state: CortexAgentState) -> Dict[str, Any]:
        task_id = state.get("request_id") or f"req_{int(time.time() * 1000)}"
        session_id = state.get("session_id") or "default_session"
        user_query = self._get_user_query(state)

        self.event_bus.publish_sync(
            EventType.AGENT_STARTED,
            task_id=task_id,
            data={"query": user_query, "session_id": session_id}
        )

        return {
            "request_id": task_id,
            "session_id": session_id,
            "retry_count": state.get("retry_count", 0),
            "tool_calls": state.get("tool_calls", []),
            "tool_results": state.get("tool_results", []),
            "optimization_candidates": state.get("optimization_candidates", [])
        }

    # 2. memory_retrieval_node
    def memory_retrieval_node(self, state: CortexAgentState) -> Dict[str, Any]:
        task_id = state.get("request_id", "")
        session_id = state.get("session_id", "default_session")
        user_query = self._get_user_query(state)

        retrieved = self.memory_mgr.retrieve_context(user_query, session_id)
        self.event_bus.publish_sync(
            EventType.MEMORY_RETRIEVED,
            task_id=task_id,
            data={"retrieved_count": len(retrieved.get("similar_episodes", []))}
        )

        return {
            "memories": retrieved.get("similar_episodes", [])
        }

    # 3. intent_router_node
    def intent_router_node(self, state: CortexAgentState) -> Dict[str, Any]:
        task_id = state.get("request_id", "")
        user_query = self._get_user_query(state)

        route_res = self.supervisor.route(user_query)
        intent = route_res.get("intent", "query")

        self.event_bus.publish_sync(
            EventType.INTENT_DETECTED,
            task_id=task_id,
            data={"intent": intent, "confidence": route_res.get("confidence", 1.0)}
        )

        return {
            "intent": intent
        }

    # 4. schema_node
    def schema_node(self, state: CortexAgentState) -> Dict[str, Any]:
        task_id = state.get("request_id", "")
        schema_summary = self.adapter.get_schema_summary()

        self.event_bus.publish_sync(
            EventType.SCHEMA_RETRIEVED,
            task_id=task_id,
            data={"schema_summary_length": len(schema_summary)}
        )

        return {
            "schema_summary": schema_summary,
            "schema": self.adapter.get_catalog_dict()
        }

    # 5. sql_agent_node
    def sql_agent_node(self, state: CortexAgentState) -> Dict[str, Any]:
        task_id = state.get("request_id", "")
        user_query = self._get_user_query(state)
        schema_summary = state.get("schema_summary", "")
        memories = json.dumps(state.get("memories", []), ensure_ascii=False)

        gen_res = self.sql_agent.generate(user_query, schema_summary, memories)
        sql = gen_res.get("sql", "").strip()

        self.event_bus.publish_sync(
            EventType.SQL_GENERATED,
            task_id=task_id,
            data={"sql": sql, "explanation": gen_res.get("explanation", "")}
        )

        return {
            "generated_sql": sql
        }

    # 6. metrics_node
    def metrics_node(self, state: CortexAgentState) -> Dict[str, Any]:
        metrics = self.adapter.get_buffer_metrics()
        diagnostics = self.adapter.get_diagnostics()
        catalog = self.adapter.get_catalog_dict()
        return {
            "tool_results": state.get("tool_results", []) + [
                {"tool": "metrics", "data": metrics},
                {"tool": "diagnostics", "data": diagnostics}
            ]
        }

    # 7. dba_agent_node
    def dba_agent_node(self, state: CortexAgentState) -> Dict[str, Any]:
        task_id = state.get("request_id", "")
        user_query = self._get_user_query(state)

        metrics = self.adapter.get_buffer_metrics()
        diagnostics = self.adapter.get_diagnostics()
        catalog = self.adapter.get_catalog_dict()

        explain_text = ""
        # 尝试对可能的慢查询执行 explain
        if "employees" in user_query.lower() or "员工" in user_query:
            slow_sample = "SELECT * FROM employees WHERE dept_id = 10;"
            exp_res = self.adapter.explain(slow_sample)
            explain_text = exp_res.get("plan", "")

        dba_res = self.dba_agent.diagnose(
            user_query=user_query,
            metrics_context=json.dumps(metrics, ensure_ascii=False, indent=2),
            explain_context=explain_text,
            catalog_context=json.dumps(catalog, ensure_ascii=False, indent=2),
            diagnostics_context=json.dumps(diagnostics, ensure_ascii=False, indent=2)
        )

        candidates = dba_res.get("recommendations", [])
        self.event_bus.publish_sync(
            EventType.ANALYSIS_COMPLETED,
            task_id=task_id,
            data={"recommendations": candidates}
        )

        # 检查候选优化项是否包含可执行的 index sql
        sql_to_run = None
        if candidates and len(candidates) > 0:
            sql_to_run = candidates[0].get("sql")

        return {
            "optimization_candidates": candidates,
            "generated_sql": sql_to_run
        }

    # 8. safety_guard_node
    def safety_guard_node(self, state: CortexAgentState) -> Dict[str, Any]:
        sql = state.get("generated_sql")
        if not sql:
            return {"approval_required": False}

        task_id = state.get("request_id", "default")
        session_id = state.get("session_id", "default")
        decision = self.firewall.inspect(sql, task_id=task_id, session_id=session_id)

        if not decision.allowed:
            if decision.action == "REQUIRE_APPROVAL":
                return {
                    "approval_required": True,
                    "approval_request_id": decision.approval_request.request_id if decision.approval_request else None,
                    "risk_level": decision.risk.risk_level.value
                }
            else:
                # DENY
                return {
                    "approval_required": False,
                    "validation": {
                        "valid": False,
                        "error_message": decision.reason,
                        "error_type": "SECURITY_FIREWALL_DENY"
                    }
                }

        return {
            "approval_required": False,
            "risk_level": decision.risk.risk_level.value
        }

    # 9. compiler_check_node
    def compiler_check_node(self, state: CortexAgentState) -> Dict[str, Any]:
        task_id = state.get("request_id", "")
        sql = state.get("generated_sql")

        # 若此前已被安全防火墙拒绝，直接透传错误
        val_state = state.get("validation")
        if val_state and not val_state.get("valid", True) and "FIREWALL" in val_state.get("error_type", ""):
            return {}

        if not sql:
            return {"validation": {"valid": True, "message": "无 SQL 需校验"}}

        val_res = self.adapter.validate(sql)
        diag = DiagnosticAdapter.parse_error(
            val_res.get("error_message", ""),
            val_res.get("error_type"),
            val_res.get("smart_hints")
        )

        self.event_bus.publish_sync(
            EventType.SQL_VALIDATED,
            task_id=task_id,
            data={"valid": val_res["valid"], "diagnostic": diag.model_dump()}
        )

        return {
            "validation": {
                "valid": val_res["valid"],
                "diagnostic": diag.model_dump(),
                "error_message": val_res.get("error_message"),
                "guidance": diag.to_correction_prompt()
            }
        }

    # 10. recovery_agent_node (Self-Healing)
    def recovery_agent_node(self, state: CortexAgentState) -> Dict[str, Any]:
        task_id = state.get("request_id", "")
        user_query = self._get_user_query(state)
        failed_sql = state.get("generated_sql", "")
        val = state.get("validation", {})
        guidance = val.get("guidance", val.get("error_message", ""))
        schema_summary = state.get("schema_summary", "")

        current_retries = state.get("retry_count", 0) + 1

        rec_res = self.recovery_agent.recover(
            user_query=user_query,
            failed_sql=failed_sql,
            diagnostic_text=guidance,
            schema_context=schema_summary
        )

        corrected_sql = rec_res.get("corrected_sql", failed_sql).strip()

        self.event_bus.publish_sync(
            EventType.SQL_CORRECTED,
            task_id=task_id,
            data={
                "failed_sql": failed_sql,
                "corrected_sql": corrected_sql,
                "retry_count": current_retries,
                "root_cause": rec_res.get("root_cause")
            }
        )

        return {
            "generated_sql": corrected_sql,
            "retry_count": current_retries
        }

    # 11. explain_node
    def explain_node(self, state: CortexAgentState) -> Dict[str, Any]:
        sql = state.get("generated_sql")
        if sql and sql.strip().upper().startswith("SELECT"):
            exp = self.adapter.explain(sql)
            return {"explain": exp}
        return {}

    # 12. execute_node
    def execute_node(self, state: CortexAgentState) -> Dict[str, Any]:
        task_id = state.get("request_id", "")
        sql = state.get("generated_sql")
        if not sql:
            return {}

        exec_res = self.adapter.execute(sql)

        self.event_bus.publish_sync(
            EventType.SQL_EXECUTED,
            task_id=task_id,
            data={
                "success": exec_res.get("success"),
                "rows_count": len(exec_res.get("data", [])),
                "latency_ms": exec_res.get("latency_ms")
            }
        )

        return {"execution_result": exec_res}

    # 13. optimization_check_node
    def optimization_check_node(self, state: CortexAgentState) -> Dict[str, Any]:
        candidates = state.get("optimization_candidates", [])
        sql = state.get("generated_sql")
        if candidates and sql and candidates[0].get("sql"):
            comp = self.optimizer_agent.compare_optimization(
                target_sql=sql,
                index_sql=candidates[0].get("sql")
            )
            return {"optimization_comparison": comp}
        return {}

    # 14. memory_update_node
    def memory_update_node(self, state: CortexAgentState) -> Dict[str, Any]:
        user_query = self._get_user_query(state)
        sql = state.get("generated_sql")
        exec_res = state.get("execution_result")

        if sql and exec_res and exec_res.get("success"):
            self.memory_mgr.record_success_experience(
                query=user_query,
                sql=sql,
                error=None,
                correction=None
            )
        return {}

    # 15. synthesizer_node
    def synthesizer_node(self, state: CortexAgentState) -> Dict[str, Any]:
        task_id = state.get("request_id", "")
        user_query = self._get_user_query(state)
        intent = state.get("intent", "query")
        sql = state.get("generated_sql", "")
        val = state.get("validation", {})
        val_status = "通过" if val.get("valid") else f"未通过 ({val.get('error_message', '')})"

        # 检查是否等待人工审批
        if state.get("approval_required"):
            req_id = state.get("approval_request_id")
            answer = (
                f"⚠️ **安全操作拦截 (Human Approval Required)**\n\n"
                f"Agent 检测到该操作涉及数据库结构/管理变更：\n"
                f"```sql\n{sql}\n```\n"
                f"- **风险级别**: `{state.get('risk_level', 'ADMIN')}`\n"
                f"- **审批单号**: `{req_id}`\n\n"
                f"请在 Web 控制台或输入 `/approve {req_id}` 确认授权后继续物理执行。"
            )
            return {"final_answer": answer}

        # 若编译检查多次失败仍无法自愈
        if not val.get("valid", True) and state.get("retry_count", 0) >= 3:
            answer = (
                f"❌ **SQL 编译质检未通过 (已达最大自愈重试上限 3 次)**\n\n"
                f"- **尝试 SQL**: `{sql}`\n"
                f"- **内核诊断报错**: `{val.get('error_message')}`\n\n"
                f"请检查表中字段是否存在或补充 Schema 信息。"
            )
            return {"final_answer": answer}

        opt_summary = ""
        comp = state.get("optimization_comparison")
        if comp:
            opt_summary = f"{comp.get('summary')} (预计改善: {comp.get('improvement_percentage')})"

        answer = self.analyst_agent.synthesize(
            user_query=user_query,
            intent=intent,
            final_sql=sql,
            validation_status=val_status,
            execution_result=state.get("execution_result"),
            optimization_summary=opt_summary
        )

        self.event_bus.publish_sync(
            EventType.AGENT_COMPLETED,
            task_id=task_id,
            data={"final_answer_length": len(answer)}
        )

        return {"final_answer": answer}
