# agent/api/routes_dba.py
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from agent.api.dependencies import get_services

router = APIRouter(prefix="/api/v1/dba", tags=["DBA"])


class OptimizeRequest(BaseModel):
    sql_or_table: str = Field(..., description="待优化的 SQL 查询或表名")


@router.get("/metrics")
def get_metrics() -> Dict[str, Any]:
    exec_svc, _, _ = get_services()
    db_metrics = exec_svc.adapter.get_buffer_metrics()
    agent_metrics = exec_svc.metrics.get_snapshot()
    return {
        "database": db_metrics,
        "agent": agent_metrics
    }


@router.get("/diagnose")
def get_diagnostics() -> Dict[str, Any]:
    exec_svc, _, _ = get_services()
    return exec_svc.adapter.get_diagnostics()


@router.post("/optimize")
def optimize_query(req: OptimizeRequest) -> Dict[str, Any]:
    exec_svc, _, _ = get_services()
    # 查找 index advisor tool
    advisor = exec_svc.graph.nodes if hasattr(exec_svc.graph, "nodes") else None
    res = exec_svc.run(query=f"优化数据库查询: {req.sql_or_table}")
    return res
