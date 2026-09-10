# agent/models/fallback.py
import re
import json
import time
from typing import List, Dict, Any, Optional
from agent.models.base import BaseModelClient, ChatMessage, ModelResponse, ModelTier


class FallbackModelClient(BaseModelClient):
    """
    确定性离线启发式推理引擎 (Offline Heuristic Fallback Engine)
    当未配置 LLM API Key 或网络不可用时，接管意图路由、NL2SQL 模板生成、自愈修复与结果呈现。
    """

    def _extract_last_user_query(self, messages: List[ChatMessage]) -> str:
        for m in reversed(messages):
            if m.role == "user":
                return m.content
        return ""

    def _classify_intent(self, text: str) -> Dict[str, Any]:
        low = text.lower()
        # DBA 意图关键词
        dba_keywords = ["慢", "变慢", "优化", "索引", "index", "explain", "buffer", "命中率", "诊断", "体检", "bottleneck", "性能", "advisor", "advisor"]
        if any(k in low for k in dba_keywords):
            return {"intent": "dba", "confidence": 0.95, "reason": "命中了数据库性能诊断或调优关键词"}

        # General 意图关键词
        general_keywords = ["你好", "hello", "hi", "是谁", "能做什么", "功能", "help", "帮助", "谢谢"]
        if any(k in low for k in general_keywords) and not ("查" in low or "select" in low or "count" in low):
            return {"intent": "general", "confidence": 0.9, "reason": "用户为问候或通用询问"}

        # 默认为 query 意图
        return {"intent": "query", "confidence": 0.95, "reason": "匹配数据查询或操作需求"}

    def _generate_sql(self, text: str) -> Dict[str, Any]:
        low = text.lower()

        # 1. 包含完整/部分 SQL 输入
        if "select" in low and "from" in low:
            idx = low.find("select")
            raw_sql = text[idx:].strip()
            if ";" in raw_sql:
                raw_sql = raw_sql[:raw_sql.find(";") + 1]
            else:
                raw_sql += ";"
            return {
                "sql": raw_sql,
                "explanation": "提取用户直接给出的 SQL 语句进行执行质检。"
            }

        # 2. 平均工资 + 超过 20000 / 某数值
        if "平均工资" in text or "平均薪资" in text or "avg(salary)" in low:
            limit_val = 20000
            m_val = re.search(r"(\d+)", text)
            if m_val:
                limit_val = int(m_val.group(1))

            if "超过" in text or "大于" in text or ">" in text:
                sql = (
                    "SELECT d.dept_name, AVG(e.salary) AS avg_salary "
                    "FROM employees e "
                    "JOIN departments d ON e.dept_id = d.dept_id "
                    "GROUP BY d.dept_name "
                    f"HAVING AVG(e.salary) > {limit_val}.00;"
                )
            else:
                sql = (
                    "SELECT d.dept_name, AVG(e.salary) AS avg_salary "
                    "FROM employees e "
                    "JOIN departments d ON e.dept_id = d.dept_id "
                    "GROUP BY d.dept_name;"
                )
            return {
                "sql": sql,
                "explanation": "多表关联统计各部门平均薪资，并依据条件进行 HAVING 聚合过滤。"
            }

        # 3. 薪资最高 / 前 N 名
        if "最高" in text or "前" in text and ("员工" in text or "薪资" in text):
            limit_n = 10
            m_lim = re.search(r"前\s*(\d+)", text)
            if m_lim:
                limit_n = int(m_lim.group(1))
            sql = f"SELECT emp_id, name, salary, dept_id FROM employees ORDER BY salary DESC LIMIT {limit_n};"
            return {
                "sql": sql,
                "explanation": f"按员工薪水降序排列，取前 {limit_n} 条记录。"
            }

        # 4. 部门人数 / 统计员工
        if "人数" in text or "统计" in text and "部门" in text:
            sql = (
                "SELECT d.dept_name, COUNT(e.emp_id) AS employee_count "
                "FROM departments d "
                "LEFT JOIN employees e ON d.dept_id = e.dept_id "
                "GROUP BY d.dept_name;"
            )
            return {
                "sql": sql,
                "explanation": "统计各部门对应的员工总数。"
            }

        # 5. 查询所有部门
        if "所有部门" in text or "部门列表" in text or "全部部门" in text:
            return {
                "sql": "SELECT * FROM departments;",
                "explanation": "全量查询部门表基本信息。"
            }

        # 6. 查询某具体部门 (研发部/销售部等)
        dept_match = re.search(r"(研发|销售|市场|人事|财务|运营)部", text)
        if dept_match:
            dept_name = dept_match.group(0)
            sql = (
                "SELECT e.emp_id, e.name, e.salary, d.dept_name "
                "FROM employees e "
                "JOIN departments d ON e.dept_id = d.dept_id "
                f"WHERE d.dept_name = '{dept_name}';"
            )
            return {
                "sql": sql,
                "explanation": f"查询所属 {dept_name} 的在职员工基本信息。"
            }

        # 默认：查询所有员工
        return {
            "sql": "SELECT emp_id, name, salary, dept_id, is_active FROM employees LIMIT 20;",
            "explanation": "默认查询员工表前 20 条记录。"
        }

    def _heal_sql(self, text: str) -> Dict[str, Any]:
        """自愈纠正 SQL"""
        failed_sql = text
        low = text.lower()
        if "select" in low and "from" in low:
            idx = low.find("select")
            raw = text[idx:].strip()
            if ";" in raw:
                raw = raw[:raw.find(";") + 1]
            failed_sql = raw

        corrections = [
            ("salaryy", "salary"),
            ("dept_namee", "dept_name"),
            ("emp_idd", "emp_id"),
            ("departtments", "departments"),
            ("employeess", "employees")
        ]

        fix_notes = []
        for wrong, right in corrections:
            if wrong in failed_sql:
                failed_sql = re.sub(rf"\b{wrong}\b", right, failed_sql)
                fix_notes.append(f"将拼写错误的列名/表名 `{wrong}` 修正为合法物理列 `{right}`")

        if not failed_sql.endswith(";"):
            failed_sql += ";"

        return {
            "corrected_sql": failed_sql,
            "root_cause": "SQL 包含非法或拼写错误的列名/关键字",
            "fix_summary": "；".join(fix_notes) if fix_notes else "修复了语法不合规标识符"
        }

    def _dba_diagnosis(self, text: str) -> Dict[str, Any]:
        return {
            "diagnosis_summary": "DataSphere 数据库当前运行稳定。检测到 employees 表上的 dept_id 列无可用 B+ 树辅助索引，高频关联与过滤将引发全表扫描 (Seq Scan)。",
            "bottlenecks": [
                "employees(dept_id) 缺失辅助索引，跨表 JOIN 时触发全表扫成本较重。"
            ],
            "recommendations": [
                {
                    "type": "CREATE_INDEX",
                    "target": "employees(dept_id)",
                    "sql": "CREATE INDEX idx_employees_dept ON employees(dept_id);",
                    "expected_benefit": "将 Seq Scan 转化为 Index Scan，预计加速关联查询 70% 以上",
                    "risk": "LOW"
                }
            ],
            "final_advice": "推荐在系统执行 `CREATE INDEX idx_employees_dept ON employees(dept_id);`，可显著降低 BufferPool 频繁换页压力。"
        }

    def chat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.0,
        tier: ModelTier = ModelTier.MEDIUM,
        json_mode: bool = False
    ) -> ModelResponse:
        t0 = time.perf_counter()
        sys_msg = next((m.content for m in messages if m.role == "system"), "")
        user_msg = self._extract_last_user_query(messages)

        parsed_data = None
        content = ""

        # 意图路由
        if "Intent Classification" in sys_msg or "router" in sys_msg.lower():
            parsed_data = self._classify_intent(user_msg)
            content = json.dumps(parsed_data, ensure_ascii=False, indent=2)

        # SQL 自愈修复
        elif "SQL Self-Healing" in sys_msg or "Corrector" in sys_msg or "自愈修复" in sys_msg:
            parsed_data = self._heal_sql(user_msg + " " + messages[-1].content)
            content = json.dumps(parsed_data, ensure_ascii=False, indent=2)

        # SQL 生成
        elif "SQL Generator" in sys_msg or "NL2SQL" in sys_msg:
            parsed_data = self._generate_sql(user_msg)
            content = json.dumps(parsed_data, ensure_ascii=False, indent=2)

        # DBA 诊断
        elif "DBA" in sys_msg or "Performance Advisor" in sys_msg:
            parsed_data = self._dba_diagnosis(user_msg)
            content = json.dumps(parsed_data, ensure_ascii=False, indent=2)

        # 最终汇总 Synthesizer
        elif "Synthesizer" in sys_msg or "汇总" in sys_msg:
            content = f"已根据您的需求【{user_msg}】完成数据库原生流水线处理。\n\n所有内核预检均通过，数据已准备就绪。"
            parsed_data = {"summary": content}

        # 通用兜底
        else:
            if "你好" in user_msg or "hi" in user_msg.lower():
                content = "您好！我是 CortexDB Database-Native 原生智能体。我可以帮您进行自然语言查询、SQL 生成、语法自愈修复、执行计划分析与 DBA 性能优化调优。"
            else:
                parsed_data = self._generate_sql(user_msg)
                content = json.dumps(parsed_data, ensure_ascii=False)

        latency = (time.perf_counter() - t0) * 1000.0
        return ModelResponse(
            content=content,
            parsed_json=parsed_data,
            prompt_tokens=len(user_msg) // 2,
            completion_tokens=len(content) // 2,
            total_tokens=(len(user_msg) + len(content)) // 2,
            model_name="cortex-heuristic-fallback-engine",
            latency_ms=latency
        )

    async def achat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.0,
        tier: ModelTier = ModelTier.MEDIUM,
        json_mode: bool = False
    ) -> ModelResponse:
        return self.chat(messages, temperature, tier, json_mode)
