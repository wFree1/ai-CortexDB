# web/server.py
import os
import sys
import json
import time
import mimetypes
import threading
from urllib.parse import urlparse, parse_qs
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# 引入项目引擎
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.database import DataSphereDB
from sql_compiler.lexer import Lexer
from sql_compiler.parser import Parser
from sql_compiler.planner import Planner

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')

# 全局数据库实例与锁
db_lock = threading.Lock()
db_instance = None


def get_db():
    global db_instance
    if db_instance is None:
        db_instance = DataSphereDB(data_dir=DATA_DIR)
    return db_instance


agent_service_instance = None


def get_agent_service():
    global agent_service_instance
    if agent_service_instance is None:
        from agent.runtime.adapter import CortexDBAdapter
        from agent.services.execution import ExecutionService
        adapter = CortexDBAdapter(db=get_db())
        agent_service_instance = ExecutionService(adapter=adapter)
    return agent_service_instance



def seed_demo_data(db: DataSphereDB):
    """预设丰富且包含各类工业级数据类型的演示数据"""
    stmts = [
        """
        CREATE TABLE IF NOT EXISTS departments (
            dept_id INT PRIMARY KEY,
            dept_name VARCHAR(50),
            budget DOUBLE,
            location VARCHAR(50)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS employees (
            emp_id BIGINT PRIMARY KEY,
            name VARCHAR(50),
            dept_id INT,
            salary DOUBLE,
            is_active BOOL,
            hire_date DATE,
            created_at DATETIME
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS products (
            prod_id INT PRIMARY KEY,
            title VARCHAR(100),
            price DECIMAL,
            stock SMALLINT,
            description TEXT
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS orders (
            order_id BIGINT PRIMARY KEY,
            emp_id BIGINT,
            total_amount DOUBLE,
            order_date DATE,
            status VARCHAR(20)
        );
        """,
        # 部门数据
        "INSERT INTO departments (dept_id, dept_name, budget, location) VALUES (10, '研发中心', 1500000.0, '北京·中关村');",
        "INSERT INTO departments (dept_id, dept_name, budget, location) VALUES (20, '市场营销部', 850000.0, '上海·陆家嘴');",
        "INSERT INTO departments (dept_id, dept_name, budget, location) VALUES (30, '产品运营部', 620000.0, '深圳·南山区');",
        "INSERT INTO departments (dept_id, dept_name, budget, location) VALUES (40, '前沿AI实验室', 2800000.0, '杭州·西湖区');",
        # 员工数据（含 BIGINT, DATE, DATETIME, BOOL, DOUBLE）
        "INSERT INTO employees (emp_id, name, dept_id, salary, is_active, hire_date, created_at) VALUES (1001, '张三', 10, 28500.50, TRUE, '2022-03-15', '2022-03-15 09:30:00');",
        "INSERT INTO employees (emp_id, name, dept_id, salary, is_active, hire_date, created_at) VALUES (1002, '李四', 10, 32000.00, TRUE, '2021-07-01', '2021-07-01 10:00:00');",
        "INSERT INTO employees (emp_id, name, dept_id, salary, is_active, hire_date, created_at) VALUES (1003, '王五', 20, 18500.00, FALSE, '2023-01-10', '2023-01-10 14:15:00');",
        "INSERT INTO employees (emp_id, name, dept_id, salary, is_active, hire_date, created_at) VALUES (1004, '赵六', 30, 21000.00, TRUE, '2023-05-20', '2023-05-20 11:00:00');",
        "INSERT INTO employees (emp_id, name, dept_id, salary, is_active, hire_date, created_at) VALUES (1005, '小明', 40, 45000.00, TRUE, '2020-11-11', '2020-11-11 09:00:00');",
        # 产品数据（含 DECIMAL, SMALLINT, TEXT）
        "INSERT INTO products (prod_id, title, price, stock, description) VALUES (1, 'Cortex-A1 边缘智能计算终端', 1299.99, 150, '搭载高性能神经拟态协处理器，支持千亿参数离线推理与流式时序分析');",
        "INSERT INTO products (prod_id, title, price, stock, description) VALUES (2, 'DataSphere 极速关系型存储引擎', 4999.00, 50, '纯原生单文件表空间设计，支持完整 ANSI SQL 体系与 B+ 树毫秒级索引');",
        "INSERT INTO products (prod_id, title, price, stock, description) VALUES (3, 'Agentic Vector 向量混合检索卡', 888.50, 300, '支持稠密与稀疏向量混合检索，内置硬件级图索引加速模组');",
        # 订单数据
        "INSERT INTO orders (order_id, emp_id, total_amount, order_date, status) VALUES (90001, 1001, 1299.99, '2026-09-01', 'COMPLETED');",
        "INSERT INTO orders (order_id, emp_id, total_amount, order_date, status) VALUES (90002, 1002, 4999.00, '2026-09-05', 'COMPLETED');",
        "INSERT INTO orders (order_id, emp_id, total_amount, order_date, status) VALUES (90003, 1004, 2188.49, '2026-09-10', 'PENDING');"
    ]
    for s in stmts:
        s = s.strip()
        if s:
            try:
                db.execute(s)
            except Exception:
                pass


def split_sql_statements(sql_text: str):
    """将包含多条 SQL 的文本按分号切分，忽略单双引号内的分号"""
    statements = []
    buf = []
    in_single = False
    in_double = False
    i = 0
    n = len(sql_text)
    while i < n:
        ch = sql_text[i]
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double

        if ch == ';' and not in_single and not in_double:
            stmt = ''.join(buf).strip()
            if stmt:
                statements.append(stmt + ';')
            buf = []
        else:
            buf.append(ch)
        i += 1

    remaining = ''.join(buf).strip()
    if remaining:
        statements.append(remaining if remaining.endswith(';') else remaining + ';')
    return statements


class StudioRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # 简化日志，避免刷屏
        pass

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, filepath, content_type='text/html'):
        if not os.path.exists(filepath):
            self.send_error(404, "File not found")
            return
        with open(filepath, 'rb') as f:
            content = f.read()
        self.send_response(200)
        self.send_header('Content-Type', f"{content_type}; charset=utf-8")
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # 静态首页与资源
        if path == '/' or path == '/index.html':
            self._send_file(os.path.join(STATIC_DIR, 'index.html'), 'text/html')
            return
        if path.startswith('/static/'):
            sub_path = path[len('/static/'):]
            target_path = os.path.join(STATIC_DIR, sub_path)
            mime_type, _ = mimetypes.guess_type(target_path)
            self._send_file(target_path, mime_type or 'application/octet-stream')
            return

        db = get_db()
        with db_lock:
            # 1) 获取所有数据库及元数据树
            if path == '/api/databases':
                dbs = db.list_databases()
                detail_list = []
                for db_name in dbs:
                    is_active = (db_name == db.current_database)
                    tbl_list = []
                    if is_active:
                        cat = db.catalog
                        for t_name in sorted(cat.list_tables()):
                            info = cat.get_table_info(t_name) or {}
                            tbl_list.append({
                                "name": t_name,
                                "columns": info.get("columns", []),
                                "primary_key": info.get("primary_key"),
                                "row_count": info.get("row_count", 0),
                            })
                    else:
                        db_path = db._get_database_path(db_name)
                        cat_path = os.path.join(db_path, "catalog.json")
                        if os.path.exists(cat_path):
                            try:
                                with open(cat_path, 'r', encoding='utf-8') as f:
                                    t_data = json.load(f)
                                if isinstance(t_data, dict):
                                    for t_name in sorted(t_data.keys()):
                                        info = t_data[t_name] or {}
                                        tbl_list.append({
                                            "name": t_name,
                                            "columns": info.get("columns", []),
                                            "primary_key": info.get("primary_key"),
                                            "row_count": info.get("row_count", 0),
                                        })
                            except Exception:
                                pass
                    detail_list.append({
                        "name": db_name,
                        "is_active": is_active,
                        "table_count": len(tbl_list),
                        "tables": tbl_list
                    })
                self._send_json({
                    "databases": dbs,
                    "current_database": db.current_database,
                    "databases_detail": detail_list
                })
                return

            if path == '/api/overview':
                catalog = db.catalog
                tables = catalog.list_tables()
                total_rows = sum(catalog.get_table_info(t).get('row_count', 0) for t in tables)
                bp = db.file_manager.buffer_pool
                hits = getattr(bp, 'cache_hits', 0)
                misses = getattr(bp, 'cache_misses', 0)
                total_access = hits + misses
                hit_rate = (hits / total_access * 100) if total_access > 0 else 100.0
                dirty_pages = len(getattr(bp, 'dirty_pages', set()))
                cached_pages = len(getattr(bp, 'page_table', {}))

                cur_path = db._get_database_path(db.current_database)
                db_file = os.path.join(cur_path, 'datasphere.db')
                file_size_kb = os.path.getsize(db_file) / 1024 if os.path.exists(db_file) else 0

                self._send_json({
                    "status": "online",
                    "database_name": db.current_database,
                    "current_database": db.current_database,
                    "databases": db.list_databases(),
                    "storage_file": f"{db.current_database}.db",
                    "file_size_kb": round(file_size_kb, 2),
                    "table_count": len(tables),
                    "total_records": total_rows,
                    "buffer_pool": {
                        "capacity": getattr(bp, 'capacity', 10),
                        "cached_pages": cached_pages,
                        "dirty_pages": dirty_pages,
                        "hit_rate_pct": round(hit_rate, 1),
                        "hits": hits,
                        "misses": misses
                    }
                })
                return

            # 2) 获取所有表列表及简要元数据
            if path == '/api/tables':
                catalog = db.catalog
                table_names = sorted(catalog.list_tables())
                result = []
                for name in table_names:
                    info = catalog.get_table_info(name)
                    cols = info.get('columns', [])
                    indexes = catalog.list_indexes(name) if hasattr(catalog, 'list_indexes') else []
                    result.append({
                        "name": name,
                        "row_count": info.get('row_count', 0),
                        "primary_key": info.get('primary_key'),
                        "column_count": len(cols),
                        "columns": cols,
                        "indexes": indexes
                    })
                self._send_json({"tables": result})
                return

            # 3) 获取指定表结构设计 (Table Schema / Design)
            if path.startswith('/api/table/') and path.endswith('/schema'):
                tbl_name = path.split('/')[3]
                catalog = db.catalog
                info = catalog.get_table_info(tbl_name)
                if not info:
                    self._send_json({"error": f"Table '{tbl_name}' not found"}, status=404)
                    return
                pk = info.get('primary_key')
                columns = []
                for c in info.get('columns', []):
                    is_pk = (c['name'] == pk)
                    columns.append({
                        "name": c['name'],
                        "type": c['type'],
                        "is_primary_key": is_pk,
                        "nullable": not is_pk,
                        "default": None,
                        "comment": ""
                    })
                self._send_json({
                    "table_name": tbl_name,
                    "primary_key": pk,
                    "row_count": info.get('row_count', 0),
                    "columns": columns,
                    "constraints": info.get('constraints', []),
                    "indexes": catalog.list_indexes(tbl_name) if hasattr(catalog, 'list_indexes') else []
                })
                return

            # 4) 获取指定表数据内容 (Table Data)
            if path.startswith('/api/table/') and path.endswith('/data'):
                tbl_name = path.split('/')[3]
                limit = int(query.get('limit', [100])[0])
                offset = int(query.get('offset', [0])[0])

                catalog = db.catalog
                info = catalog.get_table_info(tbl_name)
                if not info:
                    self._send_json({"error": f"Table '{tbl_name}' not found"}, status=404)
                    return

                # 直接查表
                sql = f"SELECT * FROM {tbl_name} LIMIT {limit} OFFSET {offset};"
                t0 = time.time()
                res = db.execute(sql)
                cost_ms = round((time.time() - t0) * 1000, 2)

                col_names = [c['name'] for c in info.get('columns', [])]
                col_defs = info.get('columns', [])
                self._send_json({
                    "table_name": tbl_name,
                    "columns": col_defs,
                    "column_names": col_names,
                    "rows": res.data or [],
                    "total_rows": info.get('row_count', 0),
                    "execution_time_ms": cost_ms,
                    "limit": limit,
                    "offset": offset
                })
                return

            # Agent 相关 GET 路由
            if path == '/api/agent/diagnose':
                svc = get_agent_service()
                self._send_json(svc.adapter.get_diagnostics())
                return

            if path == '/api/agent/metrics':
                svc = get_agent_service()
                self._send_json({
                    "database": svc.adapter.get_buffer_metrics(),
                    "agent": svc.metrics.get_snapshot()
                })
                return

            if path == '/api/agent/pending_approvals':
                svc = get_agent_service()
                pending = svc.firewall.approval_mgr.list_pending()
                self._send_json([p.dict() for p in pending])
                return

        self.send_error(404, "Endpoint not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_len = int(self.headers.get('Content-Length', 0))
        post_body = self.rfile.read(content_len) if content_len > 0 else b'{}'
        try:
            req_data = json.loads(post_body.decode('utf-8'))
        except Exception:
            req_data = {}

        db = get_db()

        # 1) 一键植入演示数据
        if path == '/api/seed_demo':
            with db_lock:
                seed_demo_data(db)
            self._send_json({"success": True, "message": "Demo tables and records loaded successfully!"})
            return

        # 切换当前激活数据库
        if path == '/api/database/switch':
            target_db = req_data.get('database', '').strip()
            if not target_db:
                self._send_json({"error": "Database name is required"}, status=400)
                return
            with db_lock:
                try:
                    msg = db.use_database(target_db)
                    self._send_json({
                        "success": True,
                        "message": msg,
                        "current_database": db.current_database,
                        "databases": db.list_databases()
                    })
                except Exception as e:
                    self._send_json({"error": str(e)}, status=400)
            return

        # 2) 执行任意 SQL 语句 (支持单条或多条批处理)
        if path == '/api/execute':
            sql_input = req_data.get('sql', '').strip()
            if not sql_input:
                self._send_json({"error": "Empty SQL query"}, status=400)
                return

            stmts = split_sql_statements(sql_input)
            results = []
            total_t0 = time.time()

            with db_lock:
                for s in stmts:
                    t0 = time.time()
                    # 尝试生成逻辑执行计划 explain
                    explain_text = None
                    try:
                        tokens = Lexer(s).tokens
                        ast = Parser(tokens).parse()
                        plan = Planner().generate_plan(ast)
                        explain_text = plan.explain()
                    except Exception:
                        pass

                    res = db.execute(s)
                    cost_ms = round((time.time() - t0) * 1000, 2)

                    # 提取列名
                    columns = []
                    if res.data and len(res.data) > 0:
                        columns = list(res.data[0].keys())

                    results.append({
                        "sql": s,
                        "success": res.success,
                        "error": res.error,
                        "message": res.message,
                        "columns": columns,
                        "data": res.data or [],
                        "row_count": len(res.data) if res.data is not None else 0,
                        "execution_time_ms": cost_ms,
                        "explain_plan": explain_text
                    })

            total_cost_ms = round((time.time() - total_t0) * 1000, 2)
            self._send_json({
                "total_statements": len(stmts),
                "total_execution_time_ms": total_cost_ms,
                "results": results,
                "current_database": db.current_database,
                "databases": db.list_databases()
            })
            return

        # Agent 相关 POST 路由
        if path == '/api/agent/chat':
            query_text = req_data.get('query', '').strip()
            session_id = req_data.get('session_id', 'studio_session')
            if not query_text:
                self._send_json({"error": "Empty query"}, status=400)
                return
            svc = get_agent_service()
            res = svc.run(query=query_text, session_id=session_id)
            self._send_json(res)
            return

        if path == '/api/agent/stream':
            query_text = req_data.get('query', '').strip()
            session_id = req_data.get('session_id', 'studio_session')
            if not query_text:
                self._send_json({"error": "Empty query"}, status=400)
                return

            # 发送 SSE 响应头
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.send_header('X-Accel-Buffering', 'no')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()

            import queue
            import re

            event_q = queue.Queue()
            stop_event = threading.Event()

            def event_listener(evt):
                if not stop_event.is_set():
                    event_q.put(('agent_event', evt))

            svc = get_agent_service()
            svc.event_bus.subscribe(event_listener)

            final_result_container = {}
            error_container = {}

            def run_agent():
                try:
                    res = svc.run(query=query_text, session_id=session_id)
                    final_result_container['res'] = res
                except Exception as ex:
                    error_container['err'] = str(ex)
                finally:
                    stop_event.set()
                    event_q.put(('agent_done', None))

            worker_thread = threading.Thread(target=run_agent, daemon=True)
            worker_thread.start()

            def send_sse(event_type: str, data_dict: dict):
                payload = f"event: {event_type}\ndata: {json.dumps(data_dict, ensure_ascii=False)}\n\n"
                self.wfile.write(payload.encode('utf-8'))
                self.wfile.flush()

            try:
                send_sse('start', {"query": query_text, "timestamp": time.time()})

                # 循环获取并推送思考推理事件
                while not stop_event.is_set() or not event_q.empty():
                    try:
                        item_type, item_data = event_q.get(timeout=0.08)
                    except queue.Empty:
                        continue

                    if item_type == 'agent_event':
                        send_sse('step', item_data.to_dict())
                    elif item_type == 'agent_done':
                        break

                if 'err' in error_container:
                    send_sse('error', {"error": error_container['err']})
                    return

                res = final_result_container.get('res', {})
                raw_answer = res.get('answer', '') or res.get('final_answer', '')

                # 检查是否有 <think>...</think> 或 <thought>...</thought> 思考块
                model_thinking = None
                clean_answer = raw_answer

                think_match = re.search(r'<think>(.*?)</think>', raw_answer, re.DOTALL)
                if think_match:
                    model_thinking = think_match.group(1).strip()
                    clean_answer = re.sub(r'<think>.*?</think>', '', raw_answer, flags=re.DOTALL).strip()
                else:
                    thought_match = re.search(r'<thought>(.*?)</thought>', raw_answer, re.DOTALL)
                    if thought_match:
                        model_thinking = thought_match.group(1).strip()
                        clean_answer = re.sub(r'<thought>.*?</thought>', '', raw_answer, flags=re.DOTALL).strip()

                if model_thinking:
                    send_sse('model_thought', {"thought": model_thinking})

                # 逐字/微批次推流打字效果 (10-15ms 拟人化流式输出)
                chunk_size = 2
                for i in range(0, len(clean_answer), chunk_size):
                    chunk = clean_answer[i:i + chunk_size]
                    send_sse('token', {"token": chunk})
                    time.sleep(0.012)

                # 发送最终完成包 (包含生成的 SQL、执行计划、执行结果及安全审批单)
                send_sse('done', {
                    "generated_sql": res.get("generated_sql"),
                    "execution_result": res.get("execution_result"),
                    "explain": res.get("explain"),
                    "needs_clarification": res.get("needs_clarification"),
                    "clarification_question": res.get("clarification_question"),
                    "approval_required": res.get("approval_required"),
                    "approval_request_id": res.get("approval_request_id"),
                    "risk_level": res.get("risk_level"),
                    "validation": res.get("validation"),
                    "retry_count": res.get("retry_count", 0),
                    "final_answer": clean_answer
                })

            except (ConnectionResetError, BrokenPipeError):
                pass
            except Exception as ex:
                try:
                    send_sse('error', {"error": str(ex)})
                except Exception:
                    pass
            finally:
                stop_event.set()
                if hasattr(svc.event_bus, 'unsubscribe'):
                    svc.event_bus.unsubscribe(event_listener)
            return

        if path == '/api/agent/approve':
            request_id = req_data.get('request_id', '')
            svc = get_agent_service()
            mgr = svc.firewall.approval_mgr
            req = mgr.get_request(request_id)
            if not req:
                self._send_json({"success": False, "error": "Approval request not found"}, status=404)
                return
            if mgr.approve(request_id):
                exec_res = svc.adapter.execute(req.sql)
                svc.hooks.trigger_on_approval(req.task_id, request_id, req.sql, "APPROVED")
                self._send_json({"success": True, "status": "APPROVED", "result": exec_res})
            else:
                self._send_json({"success": False, "error": "Request cannot be approved"}, status=400)
            return

        if path == '/api/agent/reject':
            request_id = req_data.get('request_id', '')
            svc = get_agent_service()
            mgr = svc.firewall.approval_mgr
            if mgr.reject(request_id):
                req = mgr.get_request(request_id)
                if req:
                    svc.hooks.trigger_on_approval(req.task_id, request_id, req.sql, "REJECTED")
                self._send_json({"success": True, "status": "REJECTED"})
            else:
                self._send_json({"success": False, "error": "Request cannot be rejected"}, status=400)
            return

        self.send_error(404, "Endpoint not found")


def start_server(port=8088):
    os.makedirs(STATIC_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    server_address = ('', port)
    httpd = ThreadingHTTPServer(server_address, StudioRequestHandler)
    print("==================================================")
    print(f"[+] DataSphere Navicat Studio is running!")
    print(f"[+] Local URL: http://localhost:{port}")
    print("==================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        httpd.server_close()


if __name__ == '__main__':
    port = 8088
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except Exception:
            pass
    start_server(port)
