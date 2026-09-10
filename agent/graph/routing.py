# agent/graph/routing.py
from typing import Literal
from agent.graph.state import CortexAgentState


def route_by_intent(state: CortexAgentState) -> Literal["sql_agent", "dba_agent", "synthesizer"]:
    """根据意图路由到对应的核心 Agent"""
    intent = (state.get("intent") or "query").lower()
    if intent == "dba":
        return "dba_agent"
    elif intent == "general":
        return "synthesizer"
    return "sql_agent"


def route_compiler_check(state: CortexAgentState) -> Literal["explain", "recovery", "synthesizer"]:
    """编译器检查路由：通过 -> Explain；失败 -> 自愈 Recovery；重试超标 -> Synthesizer"""
    val = state.get("validation") or {}
    if val.get("valid") is True:
        return "explain"

    # 若验证失败，检查自愈重试次数 (上限 3 次)
    retries = state.get("retry_count", 0)
    if retries < 3:
        return "recovery"

    return "synthesizer"


def route_approval_check(state: CortexAgentState) -> Literal["execute", "synthesizer"]:
    """安全与人工审批路由：若需要人工审批拦截则挂起转向 Synthesizer 输出提示，否则继续物理执行"""
    if state.get("approval_required") is True:
        return "synthesizer"
    return "execute"
