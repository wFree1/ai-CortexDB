"""HTTP contract checks for the unified FastAPI Web Studio."""

import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from agent.api.app import app
from agent.hooks.base import HookManager
from agent.runtime.events import EventBus, EventType
from agent.runtime.adapter import CortexDBAdapter
from agent.security.firewall import SQLFirewall
from agent.tools.base import RiskLevel
from engine.database import DataSphereDB
from observability.metrics import MetricsCollector


class FakeService:
    def __init__(self, db):
        self.adapter = CortexDBAdapter(db=db)
        self.event_bus = EventBus()
        self.metrics = MetricsCollector()
        self.firewall = SQLFirewall()
        self.hooks = HookManager()

    def run(self, query, session_id, task_id=None):
        task_id = task_id or "chat-task"
        self.event_bus.publish_sync(EventType.AGENT_STARTED, task_id, {"query": query})
        self.event_bus.publish_sync(EventType.AGENT_STARTED, "other-task", {"query": "other"})
        return {
            "answer": "查询完成",
            "final_answer": "查询完成",
            "task_id": task_id,
            "session_id": session_id,
            "generated_sql": "SELECT * FROM sample;",
            "retry_count": 0,
        }


class StudioFastAPITest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = DataSphereDB(data_dir=self.temp_dir.name)
        self.service = FakeService(self.db)
        self.services_patch = patch(
            "web.studio_routes.get_services",
            return_value=(self.service, None, None),
        )
        self.services_patch.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.services_patch.stop()
        self.db.close()
        self.temp_dir.cleanup()

    def test_studio_page_and_database_routes(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/static/app.js").status_code, 200)
        self.assertEqual(self.client.get("/health").status_code, 200)
        paths = self.client.get("/openapi.json").json()["paths"]
        self.assertIn("/api/agent/stream", paths)
        self.assertIn("/api/v1/agent/chat", paths)

        sql = (
            "CREATE TABLE sample (id INT PRIMARY KEY, name VARCHAR(20));"
            "INSERT INTO sample (id, name) VALUES (1, 'Alice');"
            "SELECT * FROM sample;"
        )
        response = self.client.post("/api/execute", json={"sql": sql})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total_statements"], 3)
        self.assertEqual(response.json()["results"][-1]["data"][0]["name"], "Alice")

        self.assertEqual(self.client.get("/api/overview").status_code, 200)
        self.assertEqual(self.client.get("/api/databases").status_code, 200)
        self.assertEqual(self.client.get("/api/tables").json()["tables"][0]["name"], "sample")
        self.assertEqual(self.client.get("/api/table/sample/schema").status_code, 200)
        self.assertEqual(self.client.get("/api/table/sample/data").json()["rows"][0]["name"], "Alice")

    def test_agent_sse_keeps_frontend_event_contract(self):
        response = self.client.post(
            "/api/agent/stream",
            json={"query": "查 sample", "session_id": "test-session"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers["content-type"])
        self.assertIn("event: start\n", response.text)
        self.assertIn("event: step\n", response.text)
        self.assertIn("event: token\n", response.text)
        self.assertIn("event: done\n", response.text)
        self.assertNotIn("other-task", response.text)
        self.assertIn('"final_answer": "查询完成"', response.text)

    def test_remaining_studio_actions(self):
        self.assertEqual(self.client.get("/api/agent/diagnose").status_code, 200)
        self.assertEqual(self.client.get("/api/agent/metrics").status_code, 200)
        self.assertEqual(
            self.client.post("/api/agent/chat", json={"query": "你好"}).json()["answer"],
            "查询完成",
        )
        current_database = self.db.current_database
        switched = self.client.post(
            "/api/database/switch", json={"database": current_database}
        )
        self.assertEqual(switched.status_code, 200)
        self.assertEqual(switched.json()["current_database"], current_database)

        self.assertTrue(self.client.post("/api/seed_demo").json()["success"])
        self.assertIn("employees", [table["name"] for table in self.client.get("/api/tables").json()["tables"]])

        manager = self.service.firewall.approval_mgr
        approval = manager.create_request(
            "task-1", "session-1",
            "INSERT INTO departments (dept_id, dept_name) VALUES (99, '测试');",
            RiskLevel.WRITE, "INSERT", "test",
        )
        self.assertEqual(len(self.client.get("/api/agent/pending_approvals").json()), 1)
        approved = self.client.post("/api/agent/approve", json={"request_id": approval.request_id})
        self.assertEqual(approved.status_code, 200)
        self.assertTrue(approved.json()["result"]["success"])

        rejection = manager.create_request(
            "task-2", "session-1", "DELETE FROM departments WHERE dept_id = 99;",
            RiskLevel.WRITE, "DELETE", "test",
        )
        rejected = self.client.post("/api/agent/reject", json={"request_id": rejection.request_id})
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.json()["status"], "REJECTED")


if __name__ == "__main__":
    unittest.main()
