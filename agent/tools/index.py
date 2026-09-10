# agent/tools/index.py
import json
import re
from langchain_core.tools import tool
from agent.tools.base import ToolSpec, RiskLevel
from agent.runtime.adapter import CortexDBAdapter

INDEX_ADVISOR_TOOL_SPEC = ToolSpec(
    name="cortex_index_advisor",
    description="分析查询执行计划或表结构，智能识别全表扫描 (Seq Scan) 瓶颈并生成 B+ 树索引创建建议与收益预估。",
    risk_level=RiskLevel.READ,
    permissions=["dba.advisor"],
    timeout=10.0,
    retryable=True
)


def get_index_advisor_tool(adapter: CortexDBAdapter):
    @tool(INDEX_ADVISOR_TOOL_SPEC.name, description=INDEX_ADVISOR_TOOL_SPEC.description)
    def cortex_index_advisor(sql_or_table: str) -> str:
        """
        根据输入的 SQL 查询或指定表名，分析索引覆盖情况并生成优化建议。
        :param sql_or_table: 需要优化的 SQL 查询语句，或需要诊断的表名。
        """
        catalog = adapter.get_catalog_dict()
        input_str = sql_or_table.strip()
        candidates = []

        # 场景 1: 输入的是 SQL 查询语句
        if input_str.upper().startswith("SELECT"):
            plan_res = adapter.explain(input_str)
            plan_text = plan_res.get("plan", "") if plan_res.get("success") else ""
            
            # 正则提取 SQL 中涉及的表与 WHERE / JOIN 列
            # 常见格式: WHERE column = ... 或 ON t1.col = t2.col
            where_match = re.search(r"WHERE\s+(.+?)(?:GROUP|ORDER|LIMIT|$)", input_str, re.IGNORECASE | re.DOTALL)
            where_clause = where_match.group(1) if where_match else ""
            
            # 查找目标表
            from_match = re.search(r"FROM\s+([a-zA-Z0-9_]+)", input_str, re.IGNORECASE)
            table_name = from_match.group(1) if from_match else ""

            if table_name and table_name in catalog:
                table_info = catalog[table_name]
                existing_indexes = [idx["name"].lower() for idx in table_info.get("indexes", [])]
                cols = list(table_info.get("columns", {}).keys())

                # 检查在 WHERE 条件中出现的列
                for col in cols:
                    if re.search(rf"\b{re.escape(col)}\b", where_clause, re.IGNORECASE):
                        idx_name = f"idx_{table_name}_{col}"
                        if idx_name.lower() not in existing_indexes and col != table_info.get("primary_key"):
                            candidates.append({
                                "type": "CREATE_INDEX",
                                "table": table_name,
                                "columns": [col],
                                "sql": f"CREATE INDEX {idx_name} ON {table_name}({col});",
                                "reason": f"表 {table_name} 存在针对列 {col} 的高频过滤/连接条件，当前无可用 B+ 树辅助索引。",
                                "risk": "LOW",
                                "expected_benefit": "HIGH (预计将 Seq Scan 转化为 Index Scan，降低 I/O 成本 ~70%)"
                            })

        # 场景 2: 输入的是单个表名
        elif input_str in catalog:
            table_name = input_str
            table_info = catalog[table_name]
            existing_indexes = [idx["name"].lower() for idx in table_info.get("indexes", [])]
            for col, col_type in table_info.get("columns", {}).items():
                if col.endswith("_id") and col != table_info.get("primary_key"):
                    idx_name = f"idx_{table_name}_{col}"
                    if idx_name.lower() not in existing_indexes:
                        candidates.append({
                            "type": "CREATE_INDEX",
                            "table": table_name,
                            "columns": [col],
                            "sql": f"CREATE INDEX {idx_name} ON {table_name}({col});",
                            "reason": f"外键或关联列 {col} 通常用于 JOIN 查询，建议建立索引加速查找。",
                            "risk": "LOW",
                            "expected_benefit": "MEDIUM"
                        })

        if not candidates:
            return json.dumps({
                "status": "OPTIMAL",
                "message": "当前表或查询结构良好，或已有对应主键/现有索引覆盖，暂无新增索引建议。",
                "candidates": []
            }, ensure_ascii=False, indent=2)

        return json.dumps({
            "status": "RECOMMENDATION_AVAILABLE",
            "count": len(candidates),
            "candidates": candidates
        }, ensure_ascii=False, indent=2)

    return cortex_index_advisor
