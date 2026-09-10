# agent/api/routes_tasks.py
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from agent.api.dependencies import get_services

router = APIRouter(prefix="/api/v1/tasks", tags=["Tasks & Approvals"])


@router.get("")
def list_tasks() -> List[Dict[str, Any]]:
    _, _, task_svc = get_services()
    return [t.dict() for t in task_svc.list_tasks()]


@router.get("/pending_approvals")
def list_pending_approvals() -> List[Dict[str, Any]]:
    exec_svc, _, _ = get_services()
    pending = exec_svc.firewall.approval_mgr.list_pending()
    return [p.dict() for p in pending]


@router.post("/{request_id}/approve")
def approve_request(request_id: str) -> Dict[str, Any]:
    exec_svc, _, _ = get_services()
    mgr = exec_svc.firewall.approval_mgr
    req = mgr.get_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Approval request not found")

    ok = mgr.approve(request_id)
    if ok:
        # 执行被批准的 SQL
        exec_res = exec_svc.adapter.execute(req.sql)
        exec_svc.hooks.trigger_on_approval(req.task_id, request_id, req.sql, "APPROVED")
        return {
            "success": True,
            "status": "APPROVED",
            "execution_result": exec_res
        }
    return {"success": False, "message": "Request cannot be approved (already resolved)"}


@router.post("/{request_id}/reject")
def reject_request(request_id: str) -> Dict[str, Any]:
    exec_svc, _, _ = get_services()
    mgr = exec_svc.firewall.approval_mgr
    ok = mgr.reject(request_id)
    if ok:
        req = mgr.get_request(request_id)
        if req:
            exec_svc.hooks.trigger_on_approval(req.task_id, request_id, req.sql, "REJECTED")
        return {"success": True, "status": "REJECTED"}
    return {"success": False, "message": "Request cannot be rejected"}
