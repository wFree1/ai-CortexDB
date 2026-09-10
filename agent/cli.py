# agent/cli.py
import sys
import os

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

if sys.platform != "win32":
    try:
        import readline
    except ImportError:
        pass
from agent.services.execution import ExecutionService
from agent.config import get_config


def main():
    cfg = get_config()
    print("=" * 65)
    print(" CortexDB Database-Native Agent Interactive CLI (V2.0)")
    print(" Core: DataSphere Storage & Compiler Engine + LangGraph Runtime")
    print(" Mode: " + ("LLM (" + cfg.model_name + ")" if cfg.has_api_key else "Offline Heuristic Fallback"))
    print(" Type your natural language question, SQL query, or /help to start.")
    print("=" * 65)

    svc = ExecutionService()
    session_id = "cli_session"

    try:
        while True:
            try:
                user_input = input("\ncortex> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nExiting CortexDB Agent CLI.")
                break

            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit", "\\q"):
                print("Bye!")
                break

            if user_input == "/help":
                print("Available commands:")
                print("  /help           - Show this help message")
                print("  /metrics        - Show BufferPool and engine metrics")
                print("  /diagnose       - Run full database health diagnosis")
                print("  /clear          - Clear current conversation memory")
                print("  /approve <id>   - Approve a pending security request")
                print("  /reject <id>    - Reject a pending security request")
                print("  <any query>     - Natural language (e.g. '查询研发部门平均工资') or SQL")
                continue

            if user_input == "/metrics":
                import json
                m = svc.adapter.get_buffer_metrics()
                print("BufferPool Metrics:")
                print(json.dumps(m, ensure_ascii=False, indent=2))
                continue

            if user_input == "/diagnose":
                import json
                d = svc.adapter.get_diagnostics()
                print("Database Health Diagnosis:")
                print(json.dumps(d, ensure_ascii=False, indent=2))
                continue

            if user_input == "/clear":
                svc.memory_mgr.conversation.clear_session(session_id)
                print("✓ Session conversation memory cleared.")
                continue

            if user_input.startswith("/approve "):
                req_id = user_input.split()[1].strip()
                mgr = svc.firewall.approval_mgr
                req = mgr.get_request(req_id)
                if req and mgr.approve(req_id):
                    print(f"✓ Approved request {req_id}. Executing SQL: {req.sql}")
                    res = svc.adapter.execute(req.sql)
                    print("Execution Result:", res)
                else:
                    print(f"❌ Failed to approve request {req_id} (not found or already resolved).")
                continue

            if user_input.startswith("/reject "):
                req_id = user_input.split()[1].strip()
                mgr = svc.firewall.approval_mgr
                if mgr.reject(req_id):
                    print(f"✓ Rejected request {req_id}.")
                else:
                    print(f"❌ Failed to reject request {req_id}.")
                continue

            print("\n[Agent Thinking] 正在解析意图与检索 Schema...")
            res = svc.run(query=user_input, session_id=session_id)

            if not res.get("success"):
                print(f"[ERROR] 执行失败: {res.get('error', '未知错误')}")
                if res.get("answer"):
                    print(res["answer"])
                continue

            sql = res.get("generated_sql")
            if sql:
                print(f"\n[Generated SQL]\n  {sql}")

            val = res.get("validation", {})
            if val.get("valid"):
                print("[OK] Compiler Validation: PASSED")
            else:
                print(f"[ERROR] Compiler Validation: FAILED ({val.get('error_message')})")

            if res.get("approval_required"):
                print(f"[WARN] Human Approval Required! (Request ID: {res.get('approval_request_id')})")
                print(f"  Type `/approve {res.get('approval_request_id')}` to authorize.")
            else:
                exec_res = res.get("execution_result")
                if exec_res and exec_res.get("success"):
                    rows = exec_res.get("data", [])
                    print(f"[OK] Execution Successful: {len(rows)} rows ({exec_res.get('latency_ms')} ms)")

            print(f"\n[Agent Response]\n{res.get('answer')}")

    finally:
        svc.close()


if __name__ == "__main__":
    main()
