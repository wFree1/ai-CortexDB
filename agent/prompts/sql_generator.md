# CortexDB SQL Generator Prompt

根据用户的自然语言需求以及提供的数据库 Schema 定义，生成完全兼容 DataSphere 关系型数据库内核的 SQL 语句。

## 目标数据库方言特性（DataSphere SQL Dialect）
- 支持标准的 `SELECT`, `FROM`, `WHERE`, `JOIN` (INNER/LEFT JOIN), `GROUP BY`, `HAVING`, `ORDER BY`, `LIMIT`。
- 支持聚合函数：`COUNT()`, `SUM()`, `AVG()`, `MIN()`, `MAX()`。
- 支持别名：`SELECT e.name AS emp_name, d.dept_name FROM employees e LEFT JOIN departments d ON e.dept_id = d.dept_id`。
- 支持比较操作符：`=`, `!=`, `<`, `<=`, `>`, `>=`, `LIKE`, `IN`, `BETWEEN ... AND ...`。
- 支持逻辑运算符：`AND`, `OR`, `NOT`。
- 严禁使用 DataSphere 不支持的方言黑魔法（如窗口函数 OVER/PARTITION BY、复杂的子查询或存储过程）。

## 输入上下文
- **用户问题**: {user_query}
- **相关 Schema**: 
{schema_context}
- **历史相关经验/记忆**:
{memory_context}

## 输出要求
请直接输出包含 `sql` 和 `explanation` 的 JSON 结构：
```json
{
  "sql": "SELECT ... FROM ... WHERE ...;",
  "explanation": "简明解释此 SQL 的查询逻辑与涉及的表和字段"
}
```
保证 SQL 以分号 `;` 结尾。
