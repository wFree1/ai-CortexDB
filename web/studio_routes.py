"""FastAPI routes used by the DataSphere Web Studio."""

import json
import os
import queue
import re
import threading
import time
import uuid
from typing import Any

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from agent.api.dependencies import get_services
from sql_compiler.lexer import Lexer
from sql_compiler.parser import Parser
from sql_compiler.planner import Planner
from web.demo import seed_demo_data, split_sql_statements


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
router = APIRouter(tags=["Web Studio"])
db_lock = threading.RLock()


class DatabaseSwitchRequest(BaseModel):
    database: str = ""


class SQLExecuteRequest(BaseModel):
    sql: str = ""


class StudioChatRequest(BaseModel):
    query: str = ""
    session_id: str = "studio_session"


class ApprovalActionRequest(BaseModel):
    request_id: str = ""


def get_db():
    """Use the same database instance as the FastAPI Agent routes."""
    return get_services()[0].adapter.db


def error_response(message: str, status_code: int) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status_code)


@router.get("/", include_in_schema=False)
@router.get("/index.html", include_in_schema=False)
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@router.get("/api/databases")
def databases():
    db = get_db()
    with db_lock:
        names = db.list_databases()
        details = []
        for db_name in names:
            is_active = db_name == db.current_database
            tables = []
            if is_active:
                catalog = db.catalog
                for name in sorted(catalog.list_tables()):
                    info = catalog.get_table_info(name) or {}
                    tables.append({
                        "name": name,
                        "columns": info.get("columns", []),
                        "primary_key": info.get("primary_key"),
                        "row_count": info.get("row_count", 0),
                    })
            else:
                catalog_path = os.path.join(db._get_database_path(db_name), "catalog.json")
                if os.path.exists(catalog_path):
                    try:
                        with open(catalog_path, encoding="utf-8") as file:
                            catalog_data = json.load(file)
                        if isinstance(catalog_data, dict):
                            for name in sorted(catalog_data):
                                info = catalog_data[name] or {}
                                tables.append({
                                    "name": name,
                                    "columns": info.get("columns", []),
                                    "primary_key": info.get("primary_key"),
                                    "row_count": info.get("row_count", 0),
                                })
                    except (OSError, ValueError, TypeError):
                        pass
            details.append({
                "name": db_name,
                "is_active": is_active,
                "table_count": len(tables),
                "tables": tables,
            })
        return {
            "databases": names,
            "current_database": db.current_database,
            "databases_detail": details,
        }


@router.get("/api/overview")
def overview():
    db = get_db()
    with db_lock:
        catalog = db.catalog
        tables = catalog.list_tables()
        total_rows = sum(catalog.get_table_info(name).get("row_count", 0) for name in tables)
        pool = db.file_manager.buffer_pool
        hits = getattr(pool, "cache_hits", 0)
        misses = getattr(pool, "cache_misses", 0)
        accesses = hits + misses
        hit_rate = hits / accesses * 100 if accesses else 100.0
        db_file = os.path.join(db._get_database_path(db.current_database), "datasphere.db")
        file_size_kb = os.path.getsize(db_file) / 1024 if os.path.exists(db_file) else 0
        return {
            "status": "online",
            "database_name": db.current_database,
            "current_database": db.current_database,
            "databases": db.list_databases(),
            "storage_file": f"{db.current_database}.db",
            "file_size_kb": round(file_size_kb, 2),
            "table_count": len(tables),
            "total_records": total_rows,
            "buffer_pool": {
                "capacity": getattr(pool, "capacity", 10),
                "cached_pages": len(getattr(pool, "page_table", {})),
                "dirty_pages": len(getattr(pool, "dirty_pages", set())),
                "hit_rate_pct": round(hit_rate, 1),
                "hits": hits,
                "misses": misses,
            },
        }


@router.get("/api/tables")
def tables():
    db = get_db()
    with db_lock:
        catalog = db.catalog
        result = []
        for name in sorted(catalog.list_tables()):
            info = catalog.get_table_info(name)
            columns = info.get("columns", [])
            indexes = catalog.list_indexes(name) if hasattr(catalog, "list_indexes") else []
            result.append({
                "name": name,
                "row_count": info.get("row_count", 0),
                "primary_key": info.get("primary_key"),
                "column_count": len(columns),
                "columns": columns,
                "indexes": indexes,
            })
        return {"tables": result}


@router.get("/api/table/{table_name}/schema")
def table_schema(table_name: str):
    db = get_db()
    with db_lock:
        catalog = db.catalog
        info = catalog.get_table_info(table_name)
        if not info:
            return error_response(f"Table '{table_name}' not found", 404)
        primary_key = info.get("primary_key")
        columns = [{
            "name": column["name"],
            "type": column["type"],
            "is_primary_key": column["name"] == primary_key,
            "nullable": column["name"] != primary_key,
            "default": None,
            "comment": "",
        } for column in info.get("columns", [])]
        return {
            "table_name": table_name,
            "primary_key": primary_key,
            "row_count": info.get("row_count", 0),
            "columns": columns,
            "constraints": info.get("constraints", []),
            "indexes": catalog.list_indexes(table_name) if hasattr(catalog, "list_indexes") else [],
        }


@router.get("/api/table/{table_name}/data")
def table_data(table_name: str, limit: int = 100, offset: int = 0):
    db = get_db()
    with db_lock:
        info = db.catalog.get_table_info(table_name)
        if not info:
            return error_response(f"Table '{table_name}' not found", 404)
        sql = f"SELECT * FROM {table_name} LIMIT {limit} OFFSET {offset};"
        start = time.time()
        result = db.execute(sql)
        return {
            "table_name": table_name,
            "columns": info.get("columns", []),
            "column_names": [column["name"] for column in info.get("columns", [])],
            "rows": result.data or [],
            "total_rows": info.get("row_count", 0),
            "execution_time_ms": round((time.time() - start) * 1000, 2),
            "limit": limit,
            "offset": offset,
        }


@router.get("/api/agent/diagnose")
def agent_diagnose():
    return get_services()[0].adapter.get_diagnostics()


@router.get("/api/agent/metrics")
def agent_metrics():
    service = get_services()[0]
    return {
        "database": service.adapter.get_buffer_metrics(),
        "agent": service.metrics.get_snapshot(),
    }


@router.get("/api/agent/pending_approvals")
def pending_approvals():
    manager = get_services()[0].firewall.approval_mgr
    return [request.model_dump() for request in manager.list_pending()]


@router.post("/api/seed_demo")
def seed_demo():
    with db_lock:
        seed_demo_data(get_db())
    return {"success": True, "message": "Demo tables and records loaded successfully!"}


@router.post("/api/database/switch")
def switch_database(request: DatabaseSwitchRequest):
    target = request.database.strip()
    if not target:
        return error_response("Database name is required", 400)
    db = get_db()
    with db_lock:
        try:
            message = db.use_database(target)
            return {
                "success": True,
                "message": message,
                "current_database": db.current_database,
                "databases": db.list_databases(),
            }
        except Exception as exc:
            return error_response(str(exc), 400)


@router.post("/api/execute")
def execute_sql(request: SQLExecuteRequest):
    sql_input = request.sql.strip()
    if not sql_input:
        return error_response("Empty SQL query", 400)
    statements = split_sql_statements(sql_input)
    results = []
    start_all = time.time()
    db = get_db()
    with db_lock:
        for sql in statements:
            start = time.time()
            explain_plan = None
            try:
                ast = Parser(Lexer(sql).tokens).parse()
                explain_plan = Planner().generate_plan(ast).explain()
            except Exception:
                pass
            result = db.execute(sql)
            results.append({
                "sql": sql,
                "success": result.success,
                "error": result.error,
                "message": result.message,
                "columns": list(result.data[0]) if result.data else [],
                "data": result.data or [],
                "row_count": len(result.data) if result.data is not None else 0,
                "execution_time_ms": round((time.time() - start) * 1000, 2),
                "explain_plan": explain_plan,
            })
        return {
            "total_statements": len(statements),
            "total_execution_time_ms": round((time.time() - start_all) * 1000, 2),
            "results": results,
            "current_database": db.current_database,
            "databases": db.list_databases(),
        }


@router.post("/api/agent/chat")
def agent_chat(request: StudioChatRequest):
    query = request.query.strip()
    if not query:
        return error_response("Empty query", 400)
    return get_services()[0].run(query=query, session_id=request.session_id)


def sse_event(event_type: str, data: dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/api/agent/stream")
def agent_stream(request: StudioChatRequest):
    query = request.query.strip()
    if not query:
        return error_response("Empty query", 400)

    service = get_services()[0]
    task_id = f"task_{uuid.uuid4().hex[:8]}"

    def events():
        event_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        stopped = threading.Event()
        result_holder: dict[str, Any] = {}

        def listener(event):
            if not stopped.is_set() and event.task_id == task_id:
                event_queue.put(("step", event.to_dict()))

        def run_agent():
            try:
                result_holder["result"] = service.run(
                    query=query,
                    session_id=request.session_id,
                    task_id=task_id,
                )
            except Exception as exc:
                result_holder["error"] = str(exc)
            finally:
                event_queue.put(("finished", None))

        service.event_bus.subscribe(listener)
        worker = threading.Thread(target=run_agent, daemon=True)
        worker.start()
        try:
            yield sse_event("start", {"query": query, "timestamp": time.time()})
            while True:
                event_type, payload = event_queue.get()
                if event_type == "finished":
                    break
                yield sse_event("step", payload)

            if "error" in result_holder:
                yield sse_event("error", {"error": result_holder["error"]})
                return

            result = result_holder.get("result", {})
            raw_answer = result.get("answer") or result.get("final_answer") or ""
            thought_match = re.search(r"<(think|thought)>(.*?)</\1>", raw_answer, re.DOTALL)
            clean_answer = raw_answer
            if thought_match:
                yield sse_event("model_thought", {"thought": thought_match.group(2).strip()})
                clean_answer = re.sub(r"<(think|thought)>.*?</\1>", "", raw_answer, flags=re.DOTALL).strip()

            # The model call is complete here; these chunks preserve the Studio typing UI.
            for start in range(0, len(clean_answer), 2):
                yield sse_event("token", {"token": clean_answer[start:start + 2]})
                time.sleep(0.012)

            yield sse_event("done", {
                "generated_sql": result.get("generated_sql"),
                "execution_result": result.get("execution_result"),
                "explain": result.get("explain"),
                "needs_clarification": result.get("needs_clarification"),
                "clarification_question": result.get("clarification_question"),
                "approval_required": result.get("approval_required"),
                "approval_request_id": result.get("approval_request_id"),
                "risk_level": result.get("risk_level"),
                "validation": result.get("validation"),
                "retry_count": result.get("retry_count", 0),
                "final_answer": clean_answer,
            })
        finally:
            stopped.set()
            service.event_bus.unsubscribe(listener)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/api/agent/approve")
def approve(request: ApprovalActionRequest):
    service = get_services()[0]
    manager = service.firewall.approval_mgr
    approval = manager.get_request(request.request_id)
    if not approval:
        return JSONResponse({"success": False, "error": "Approval request not found"}, status_code=404)
    if not manager.approve(request.request_id):
        return JSONResponse({"success": False, "error": "Request cannot be approved"}, status_code=400)
    result = service.adapter.execute(approval.sql)
    service.hooks.trigger_on_approval(approval.task_id, request.request_id, approval.sql, "APPROVED")
    return {"success": True, "status": "APPROVED", "result": result}


@router.post("/api/agent/reject")
def reject(request: ApprovalActionRequest):
    service = get_services()[0]
    manager = service.firewall.approval_mgr
    if not manager.reject(request.request_id):
        return JSONResponse({"success": False, "error": "Request cannot be rejected"}, status_code=400)
    approval = manager.get_request(request.request_id)
    if approval:
        service.hooks.trigger_on_approval(approval.task_id, request.request_id, approval.sql, "REJECTED")
    return {"success": True, "status": "REJECTED"}
