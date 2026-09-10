# tests/test_agent.py
import unittest
import os
import shutil
import json
from fastapi.testclient import TestClient

from agent.runtime.adapter import CortexDBAdapter
from agent.tools.registry import create_default_registry
from agent.models.router import ModelRouter
from agent.models.base import ChatMessage, ModelTier
from agent.models.fallback import FallbackModelClient
from agent.memory.manager import MemoryManager
from agent.security.firewall import SQLFirewall
from agent.security.policy import SecurityPolicy
from agent.tools.base import RiskLevel
from agent.services.execution import ExecutionService
from agent.api.app import app
from engine.database import DataSphereDB


class TestCortexDBAgent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_data_dir = "data_test_agent"
        os.makedirs(cls.test_data_dir, exist_ok=True)
        cls.db = DataSphereDB(data_dir=cls.test_data_dir)
        cls.db.execute("CREATE TABLE test_emp (id INT PRIMARY KEY, name VARCHAR(50), salary DOUBLE, dept_id INT);")
        cls.db.execute("INSERT INTO test_emp (id, name, salary, dept_id) VALUES (1, 'Alice', 25000.0, 10);")
        cls.db.execute("INSERT INTO test_emp (id, name, salary, dept_id) VALUES (2, 'Bob', 18000.0, 20);")
        cls.db.execute("CREATE TABLE employees (emp_id BIGINT PRIMARY KEY, name VARCHAR(50), salary DOUBLE, dept_id INT, is_active BOOL);")
        cls.db.execute("INSERT INTO employees (emp_id, name, salary, dept_id, is_active) VALUES (101, 'Charlie', 30000.0, 10, TRUE);")
        cls.db.execute("CREATE TABLE departments (dept_id INT PRIMARY KEY, dept_name VARCHAR(50));")
        cls.db.execute("INSERT INTO departments (dept_id, dept_name) VALUES (10, '研发中心');")
        cls.adapter = CortexDBAdapter(db=cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        if os.path.exists(cls.test_data_dir):
            shutil.rmtree(cls.test_data_dir, ignore_errors=True)

    # 1. Native Adapter Tests
    def test_01_adapter_operations(self):
        # execute
        res = self.adapter.execute("SELECT * FROM test_emp;")
        self.assertTrue(res["success"])
        self.assertEqual(len(res["data"]), 2)

        # validate
        val = self.adapter.validate("SELECT * FROM test_emp WHERE salary > 20000;")
        self.assertTrue(val["valid"])

        # invalid compile precheck
        invalid_val = self.adapter.validate("SELECT unknown_col FROM test_emp;")
        self.assertFalse(invalid_val["valid"])

        # explain
        exp = self.adapter.explain("SELECT * FROM test_emp WHERE id = 1;")
        self.assertTrue(exp["success"])

        # schema & metrics
        schema = self.adapter.get_schema_summary()
        self.assertIn("test_emp", schema)
        metrics = self.adapter.get_buffer_metrics()
        self.assertIn("cache_hit_rate_pct", metrics)
        diagnostics = self.adapter.get_diagnostics()
        self.assertEqual(diagnostics["health_status"], "HEALTHY")

    # 2. Tool Registry Tests (8 Tools)
    def test_02_tool_registry(self):
        reg = create_default_registry(self.adapter)
        tools = reg.list_tools()
        self.assertEqual(len(tools), 8)
        names = [t.name for t in tools]
        expected = [
            "cortex_schema", "cortex_sql_compile", "cortex_sql_execute",
            "cortex_explain", "cortex_catalog", "cortex_metrics",
            "cortex_index_advisor", "cortex_diagnostics"
        ]
        for exp in expected:
            self.assertIn(exp, names)

        # Test tool invocation
        schema_tool = reg.get("cortex_schema")
        schema_out = schema_tool.invoke({})
        self.assertIn("test_emp", schema_out)

        compile_tool = reg.get("cortex_sql_compile")
        comp_out = json.loads(compile_tool.invoke({"sql": "SELECT * FROM test_emp;"}))
        self.assertTrue(comp_out["valid"])

    # 3. Model Router & Offline Fallback Tests
    def test_03_model_router_and_fallback(self):
        router = ModelRouter()
        fallback = FallbackModelClient()

        # Intent classification
        intent_res = fallback._classify_intent("帮我做一次系统体检和性能诊断")
        self.assertEqual(intent_res["intent"], "dba")

        intent_query = fallback._classify_intent("查询薪资最高的员工")
        self.assertEqual(intent_query["intent"], "query")

        # SQL generation
        sql_res = fallback._generate_sql("查询部门平均工资超过20000的部门")
        self.assertIn("SELECT", sql_res["sql"])
        self.assertIn("AVG", sql_res["sql"])
        self.assertIn("GROUP BY", sql_res["sql"])

        # Self-healing typo correction
        healed = fallback._heal_sql("SELECT name, salaryy FROM employees;")
        self.assertIn("salary", healed["corrected_sql"])
        self.assertNotIn("salaryy", healed["corrected_sql"])

    # 4. Multi-Memory Tests (6 Layers)
    def test_04_multi_memory_architecture(self):
        mm = MemoryManager()
        # Working
        mm.working.set("current_task", "query_salary")
        self.assertEqual(mm.working.get("current_task"), "query_salary")

        # Conversation
        mm.conversation.add_message("sess_1", "user", "hi")
        self.assertEqual(len(mm.conversation.get_messages("sess_1")), 1)

        # Schema cache
        mm.schema.set("summary", "table employees")
        self.assertEqual(mm.schema.get("summary"), "table employees")

        # Semantic
        self.assertIn("员工", mm.semantic.get_synonyms())

        # Episodic
        mm.record_success_experience("查询员工", "SELECT * FROM test_emp;")
        ctx = mm.retrieve_context("查询员工", "sess_1")
        self.assertEqual(len(ctx["similar_episodes"]), 1)

        # Preference
        self.assertEqual(mm.preference.get("format"), "markdown")

    # 5. Security Policy & SQL Firewall Tests
    def test_05_security_firewall(self):
        fw = SQLFirewall()

        # READ statement -> ALLOW
        dec_read = fw.inspect("SELECT * FROM test_emp;")
        self.assertEqual(dec_read.action, "ALLOW")

        # DANGEROUS statement -> DENY
        dec_drop = fw.inspect("DROP TABLE test_emp;")
        self.assertEqual(dec_drop.action, "DENY")
        self.assertEqual(dec_drop.risk.risk_level, RiskLevel.DANGEROUS)

        # ADMIN statement -> REQUIRE_APPROVAL
        dec_admin = fw.inspect("CREATE INDEX idx_emp_dept ON test_emp(dept_id);")
        self.assertEqual(dec_admin.action, "REQUIRE_APPROVAL")
        self.assertIsNotNone(dec_admin.approval_request)

    # 6. LangGraph Multi-Agent Workflow Tests
    def test_06_langgraph_workflow_and_self_healing(self):
        svc = ExecutionService(adapter=self.adapter)

        # Normal Query Flow
        res = svc.run(query="SELECT * FROM test_emp;")
        self.assertTrue(res["success"])
        self.assertEqual(len(res["execution_result"]["data"]), 2)

        # Self-Healing Flow (deliberate unknown column salaryy)
        res_heal = svc.run(query="SELECT name, salaryy FROM test_emp;")
        self.assertTrue(res_heal["success"])
        self.assertGreaterEqual(res_heal["retry_count"], 1)
        self.assertIn("salary", res_heal["generated_sql"])

        # DBA Diagnosis Flow
        res_dba = svc.run(query="为什么 test_emp 表查询变慢了？请诊断")
        self.assertTrue(res_dba["success"])
        self.assertEqual(res_dba["intent"], "dba")

    # 7. FastAPI Endpoints & Observability Tests
    def test_07_fastapi_endpoints(self):
        client = TestClient(app)

        # Health
        res_health = client.get("/health")
        self.assertEqual(res_health.status_code, 200)

        # Chat
        res_chat = client.post("/api/v1/agent/chat", json={"query": "SELECT * FROM employees;"})
        self.assertEqual(res_chat.status_code, 200)
        self.assertTrue(res_chat.json().get("success"))

        # SQL Validate
        res_val = client.post("/api/v1/sql/validate", json={"sql": "SELECT * FROM employees;"})
        self.assertEqual(res_val.status_code, 200)
        self.assertTrue(res_val.json().get("valid"))

        # Metrics
        res_met = client.get("/api/v1/dba/metrics")
        self.assertEqual(res_met.status_code, 200)
        self.assertIn("database", res_met.json())
        self.assertIn("agent", res_met.json())


if __name__ == "__main__":
    unittest.main()
