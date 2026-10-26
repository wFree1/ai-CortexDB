from engine.database import DataSphereDB


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
