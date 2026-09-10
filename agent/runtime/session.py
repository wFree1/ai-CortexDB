# agent/runtime/session.py
import time
import uuid
from typing import Dict, Any, List, Optional
from agent.runtime.adapter import CortexDBAdapter


class DatabaseSession:
    """
    单个请求/任务绑定的数据库会话 (Database Session).
    跟踪会话内的执行操作、编译质检与耗时。
    """
    def __init__(self, adapter: CortexDBAdapter, session_id: Optional[str] = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.adapter = adapter
        self.created_at = time.time()
        self.last_active_at = time.time()
        self.query_count = 0
        self.is_closed = False

    def execute(self, sql: str) -> Dict[str, Any]:
        self.last_active_at = time.time()
        self.query_count += 1
        return self.adapter.execute(sql)

    def validate(self, sql: str) -> Dict[str, Any]:
        self.last_active_at = time.time()
        return self.adapter.validate(sql)

    def explain(self, sql: str) -> Dict[str, Any]:
        self.last_active_at = time.time()
        return self.adapter.explain(sql)

    def get_schema_summary(self, target_tables: Optional[List[str]] = None) -> str:
        self.last_active_at = time.time()
        return self.adapter.get_schema_summary(target_tables)

    def get_catalog_dict(self) -> Dict[str, Any]:
        self.last_active_at = time.time()
        return self.adapter.get_catalog_dict()

    def get_buffer_metrics(self) -> Dict[str, Any]:
        self.last_active_at = time.time()
        return self.adapter.get_buffer_metrics()

    def get_diagnostics(self) -> Dict[str, Any]:
        self.last_active_at = time.time()
        return self.adapter.get_diagnostics()

    def close(self):
        self.is_closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
