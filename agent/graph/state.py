# agent/graph/state.py
from typing import TypedDict, Optional, List, Dict, Any


class CortexAgentState(TypedDict, total=False):
    request_id: str
    session_id: str

    messages: List[Dict[str, Any]]

    intent: Optional[str]

    schema: Optional[Dict[str, Any]]
    schema_summary: Optional[str]

    memories: List[Dict[str, Any]]

    generated_sql: Optional[str]
    needs_clarification: bool
    clarification_question: Optional[str]
    clarification_reason: Optional[str]

    validation: Optional[Dict[str, Any]]

    explain: Optional[Dict[str, Any]]

    risk_level: Optional[str]

    approval_required: bool
    approval_request_id: Optional[str]

    retry_count: int

    tool_calls: List[Dict[str, Any]]
    tool_results: List[Dict[str, Any]]

    execution_result: Optional[Dict[str, Any]]

    optimization_candidates: List[Dict[str, Any]]
    optimization_comparison: Optional[Dict[str, Any]]

    final_answer: Optional[str]
