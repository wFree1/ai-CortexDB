# agent/api/routes_sql.py
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from agent.api.dependencies import get_services

router = APIRouter(prefix="/api/v1/sql", tags=["SQL"])


class SQLRequest(BaseModel):
    sql: str = Field(..., description="SQL 语句")


@router.post("/execute")
def execute_sql(req: SQLRequest) -> Dict[str, Any]:
    exec_svc, _, _ = get_services()
    return exec_svc.adapter.execute(req.sql)


@router.post("/validate")
def validate_sql(req: SQLRequest) -> Dict[str, Any]:
    exec_svc, _, _ = get_services()
    return exec_svc.adapter.validate(req.sql)


@router.post("/explain")
def explain_sql(req: SQLRequest) -> Dict[str, Any]:
    exec_svc, _, _ = get_services()
    return exec_svc.adapter.explain(req.sql)
