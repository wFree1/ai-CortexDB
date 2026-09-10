# agent/graph/graph.py
from langgraph.graph import StateGraph, START, END
from agent.graph.state import CortexAgentState
from agent.graph.nodes import GraphNodes
from agent.graph.routing import route_by_intent, route_compiler_check, route_approval_check

from agent.runtime.adapter import CortexDBAdapter
from agent.models.base import BaseModelClient
from agent.memory.manager import MemoryManager
from agent.runtime.events import EventBus
from agent.security.firewall import SQLFirewall


def build_cortex_graph(
    adapter: CortexDBAdapter,
    model_client: BaseModelClient,
    memory_mgr: MemoryManager,
    event_bus: EventBus,
    firewall: SQLFirewall
):
    """
    构建并编译 Database-Native Agent Runtime 核心状态图
    支持意图路由、Schema 动态精简召回、编译器前置预检、自愈纠错与人工审批
    """
    nodes = GraphNodes(adapter, model_client, memory_mgr, event_bus, firewall)
    workflow = StateGraph(CortexAgentState)

    # 1. 注册图节点
    workflow.add_node("context", nodes.context_node)
    workflow.add_node("memory_retrieval", nodes.memory_retrieval_node)
    workflow.add_node("intent_router", nodes.intent_router_node)
    workflow.add_node("schema", nodes.schema_node)
    workflow.add_node("sql_agent", nodes.sql_agent_node)
    workflow.add_node("metrics", nodes.metrics_node)
    workflow.add_node("dba_agent", nodes.dba_agent_node)
    workflow.add_node("safety_guard", nodes.safety_guard_node)
    workflow.add_node("compiler_check", nodes.compiler_check_node)
    workflow.add_node("recovery", nodes.recovery_agent_node)
    workflow.add_node("explain", nodes.explain_node)
    workflow.add_node("execute", nodes.execute_node)
    workflow.add_node("optimization_check", nodes.optimization_check_node)
    workflow.add_node("memory_update", nodes.memory_update_node)
    workflow.add_node("synthesizer", nodes.synthesizer_node)

    # 2. 编排边连接
    workflow.add_edge(START, "context")
    workflow.add_edge("context", "memory_retrieval")
    workflow.add_edge("memory_retrieval", "intent_router")

    # 意图分流
    workflow.add_conditional_edges(
        "intent_router",
        route_by_intent,
        {
            "sql_agent": "schema",
            "dba_agent": "metrics",
            "synthesizer": "synthesizer"
        }
    )

    workflow.add_edge("schema", "sql_agent")
    workflow.add_edge("sql_agent", "safety_guard")

    workflow.add_edge("metrics", "dba_agent")
    workflow.add_edge("dba_agent", "safety_guard")

    workflow.add_edge("safety_guard", "compiler_check")

    # 编译质检分支 (通过 -> explain; 失败 -> recovery 自愈; 超过上限 -> synthesizer)
    workflow.add_conditional_edges(
        "compiler_check",
        route_compiler_check,
        {
            "explain": "explain",
            "recovery": "recovery",
            "synthesizer": "synthesizer"
        }
    )

    # 自愈纠正后重新进入安全门禁与编译校验
    workflow.add_edge("recovery", "safety_guard")

    # 人工审批决策 (通过 -> execute; 拦截 -> synthesizer)
    workflow.add_conditional_edges(
        "explain",
        route_approval_check,
        {
            "execute": "execute",
            "synthesizer": "synthesizer"
        }
    )

    workflow.add_edge("execute", "optimization_check")
    workflow.add_edge("optimization_check", "memory_update")
    workflow.add_edge("memory_update", "synthesizer")
    workflow.add_edge("synthesizer", END)

    return workflow.compile()
