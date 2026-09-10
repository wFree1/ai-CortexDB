-- 1) CREATE：包含主键 & VARCHAR(n)
--    A. 列级主键   B. 表级主键   C. VARCHAR(上限) 与裸 VARCHAR
-- ====================================================================

-- A) 列级主键 + VARCHAR(20)
CREATE TABLE student(
  id   INT PRIMARY KEY,
  name VARCHAR(20),
  age  INT
);

-- B) 表级主键 + 裸 VARCHAR（无限长度，由运行时按字符串处理）
CREATE TABLE class(
  sid  INT,
  name VARCHAR,
  PRIMARY KEY(sid)
);

-- C) 另一个有长度限制的 VARCHAR，用于越界测试
CREATE TABLE dept(
  id     INT PRIMARY KEY,
  dname  VARCHAR(8)
);

-- ====================================================================
-- 2) INSERT：合法多行插入 + 触发主键/长度校验的报错示例
-- ====================================================================

-- student：多行插入（覆盖正常路径）
INSERT INTO student(id, name, age) VALUES
  (1, 'Alice', 20),
  (2, 'Bob',   21),
  (3, 'Cindy', 20);

-- class：多行插入（正常）
INSERT INTO class(sid, name) VALUES
  (1, 'CS101'),
  (2, 'CS102'),
  (3, 'CS101');

-- dept：正常插入
INSERT INTO dept(id, dname) VALUES
  (10, 'Math'),
  (11, 'Physics');

-- —— 预期：主键冲突（student.id 已存在 1）——
-- 期望报错：Primary key violation: 'id'=1 already exists in 'student'
-- INSERT INTO student(id, name, age) VALUES (1, 'Dup', 99);

-- —— 预期：VARCHAR 长度越界（dept.dname 为 VARCHAR(8)）——
-- 期望报错：Value too long: column 'dname' is VARCHAR(8), got length 12
-- INSERT INTO dept(id, dname) VALUES (12, 'Engineering');  -- 12字符

-- —— 预期：类型校验（把字符串塞给 INT，按你的执行器应抛错）——
-- 期望报错：Type error: column 'age' expects INT, got 'twenty'
-- INSERT INTO student(id, name, age) VALUES (4, 'TypeBad', 'twenty');

-- ====================================================================
-- 3) SELECT：基本过滤 / 排序
-- ====================================================================

SELECT id, name FROM student WHERE age > 18 ORDER BY name;

-- order by
SELECT id, name FROM student ORDER BY name ASC;
SELECT id, age  FROM student WHERE age > 18 ORDER BY age DESC;

-- ====================================================================
-- 4) UPDATE：含 VARCHAR(n) 长度校验
-- ====================================================================

-- 正常：更新年龄与名字
UPDATE student SET age = 21, name = 'Bob' WHERE id = 3;

-- —— 预期：VARCHAR 长度越界（把 dept.dname 更新为超过 8 的字符串）——
-- 期望报错：Value too long: column 'dname' is VARCHAR(8), got length 14
-- UPDATE dept SET dname = 'VeryLongName' WHERE id = 10;

-- ====================================================================
-- 5) DELETE：按主键删除一条
-- ====================================================================

DELETE FROM student WHERE id = 1;

-- ====================================================================
-- 6) JOIN：等值连接（student ↔ class）
-- ====================================================================

SELECT s.id, s.name
FROM student s JOIN class c ON s.id = c.sid;

-- 可显示把各自表的条件下推到各自 SeqScan 的例子
SELECT s.id, s.name
FROM student s JOIN class c ON s.id = c.sid
WHERE s.age > 18 AND c.name = 'CS101';

-- ====================================================================
-- 7) GROUP BY：单表与 JOIN 后分组
-- ====================================================================

-- 示例1：单表分组
SELECT age FROM student GROUP BY age;

-- 示例2：JOIN 后分组，按未限定列（你的文法允许）
SELECT s.age FROM student s JOIN class c ON s.id = c.sid GROUP BY age;





-- 测试 CREATE
CREATE TABLE student(id INT, name VARCHAR, age INT);
CREATE TABLE class(sid INT, name VARCHAR);

-- 测试 INSERT（补充多行，便于分组）
INSERT INTO student(id, name, age) VALUES (1, 'Alice', 20);
INSERT INTO student(id, name, age) VALUES (2, 'Bob',   21);
INSERT INTO student(id, name, age) VALUES (3, 'Cindy', 20);

INSERT INTO class(sid, name) VALUES (1, 'CS101');
INSERT INTO class(sid, name) VALUES (2, 'CS102');
INSERT INTO class(sid, name) VALUES (3, 'CS101');

-- 测试 SELECT
SELECT id, name FROM student WHERE age > 18 ORDER BY name;

-- 测试 DELETE
DELETE FROM student WHERE id = 1;

-- 测试 UPDATE
UPDATE student SET age = 21, name = 'Bob' WHERE id = 3;

-- 测试 JOIN
SELECT s.id, s.name FROM student s JOIN class c ON s.id = c.sid;

-- 测试 GROUP BY（示例1：单表分组，按 student.age）
SELECT age FROM student GROUP BY age;

-- 测试 GROUP BY（示例2：JOIN 后分组，仍按未限定列 age）
-- 注意：你的文法只允许 GROUP BY IDENTIFIER，因此这里使用未限定的 age
SELECT s.age FROM student s JOIN class c ON s.id = c.sid GROUP BY age;

-- order by
SELECT id, name FROM student ORDER BY name ASC;
SELECT id, age FROM student WHERE age > 18 ORDER BY age DESC;

-- 可显示把各自表的条件下推到各自 SeqScan 的例子
SELECT s.id, s.name
FROM student s JOIN class c ON s.id = c.sid
WHERE s.age > 18 AND c.name = 'CS101';



-- 智能纠错 --
-- 1) JOIN 后缺少 ON（会提示“在 JOIN 之后应有 ON ... 条件，是否缺少连接条件？”）
SELECT s.id FROM student s JOIN class c;

-- 2) JOIN 后用 WHERE 了（还是缺 ON，提示同上 + 可能提示 ON 后要跟条件）
SELECT * FROM a JOIN b WHERE a.id = b.id;

-- 3) ON 后缺布尔条件（会提示“ON / WHERE 后应跟布尔条件，例如 a.id = b.sid 或 age > 18”）
SELECT * FROM a JOIN b ON ;

-- 4) WHERE 后缺布尔条件（同样会提示“ON / WHERE 后应跟布尔条件 …”）
SELECT * FROM users WHERE ;

-- 5) WHERE 后直接 GROUP（仍会提示 WHERE 后应跟条件）
SELECT * FROM users WHERE GROUP BY id;

-- 6) ORDER BY 后缺列（会提示“ORDER BY / GROUP BY 后应跟列名 …”）
SELECT id FROM users ORDER BY ;

-- 7) GROUP BY 后缺列（同上提示）
SELECT id FROM users GROUP BY ;

-- 8) SELECT 列表缺少列（会提示“是否缺少选择列表？你可以写具体列名或使用 * …”）
SELECT FROM users;

-- 9) 语句末尾缺分号（会提示“语句末尾需要分号 ';'”）
SELECT * FROM users

-- 10) 组合错误：JOIN 缺 ON 且 WHERE 缺条件（双重命中，上面两个提示都可能出现）
SELECT s.id, s.name FROM student s JOIN class c WHERE ;

-- 正确
SELECT s.id, s.name FROM student s JOIN class c ON s.id = c.sid WHERE s.age > 18;

-- 故意漏 ON，触发 JOIN 智能提示
SELECT s.id, s.name FROM student s JOIN class c WHERE s.age > 18;


-- 谓词下推 --

-- 例子1：单表条件 + 多表 JOIN
SELECT s.id, c.name
FROM student s
JOIN class c ON s.id = c.sid
WHERE s.age > 18 AND c.name = 'CS101';

-- 例子2：混合条件，部分可下推，部分残余
SELECT s.id, c.name
FROM student s
JOIN class c ON s.id = c.sid
WHERE s.age > 18 AND c.name = 'CS101' AND s.id = c.sid;


-- 3.1 统计学生总数
SELECT COUNT(*) FROM student;

-- 3.2 求平均年龄
SELECT AVG(age) FROM student;

-- 3.3 按年龄分组统计人数
SELECT age, COUNT(*) FROM student GROUP BY age ORDER BY age DESC;


-- 外键测试 --

-- 1. 创建部门表
CREATE TABLE departments(
    dept_id INT,
    dept_name VARCHAR
);

-- 2. 创建员工表，带外键
CREATE TABLE employees(
    emp_id INT,
    emp_name VARCHAR,
    dept_id INT,
    FOREIGN KEY (dept_id) REFERENCES departments(dept_id)
);

-- 3. 插入一行部门
INSERT INTO departments(dept_id, dept_name)
VALUES (1, 'HR');

-- 4. 插入一行员工，dept_id = 1 外键存在 ✅
INSERT INTO employees(emp_id, emp_name, dept_id)
VALUES (101, 'Alice', 1);

-- 5. 查询员工姓名，带条件
SELECT emp_name FROM employees WHERE dept_id = 1;

-- 错误用例 --
-- 1. 插入员工，但 dept_id=99 在 departments 不存在
INSERT INTO employees(emp_id, emp_name, dept_id)
VALUES (102, 'Bob', 99);

-- 2. 插入部门，列数与值数不一致
INSERT INTO departments(dept_id, dept_name)
VALUES (2);


-- 测试GROUP BY和ORDER BY
-- 1. 创建 departments 表
CREATE TABLE departments (
    dept_id INT,
    dept_name VARCHAR
);

-- 2. 创建 employees 表，并添加外键约束
CREATE TABLE employees (
    emp_id INT,
    name VARCHAR,
    salary FLOAT,
    department_id INT,
    FOREIGN KEY (department_id) REFERENCES departments(dept_id)
);

-- 3. 向 departments 表插入数据
INSERT INTO departments(dept_id, dept_name) VALUES (1, 'Engineering');
INSERT INTO departments(dept_id, dept_name) VALUES (2, 'Sales');
INSERT INTO departments(dept_id, dept_name) VALUES (3, 'Marketing');
INSERT INTO departments(dept_id, dept_name) VALUES (4, 'Human Resources');

-- 4. 向 employees 表插入数据
INSERT INTO employees(emp_id, name, salary, department_id) VALUES (101, 'Alice', 75000.00, 1);
INSERT INTO employees(emp_id, name, salary, department_id) VALUES (102, 'Bob', 65000.00, 1);
INSERT INTO employees(emp_id, name, salary, department_id) VALUES (103, 'Charlie', 55000.00, 2);
INSERT INTO employees(emp_id, name, salary, department_id) VALUES (104, 'Diana', 60000.00, 2);
INSERT INTO employees(emp_id, name, salary, department_id) VALUES (105, 'Eve', 70000.00, 3);
INSERT INTO employees(emp_id, name, salary, department_id) VALUES (106, 'Frank', 50000.00, 3);
INSERT INTO employees(emp_id, name, salary, department_id) VALUES (107, 'Grace', 80000.00, 1);
INSERT INTO employees(emp_id, name, salary, department_id) VALUES (108, 'Heidi', 45000.00, 4);
INSERT INTO employees(emp_id, name, salary, department_id) VALUES (109, 'Ivan', 90000.00, 1); -- Engineering 部门的高薪员工

-- 测试用例 1: 基础分组与聚合
-- 统计每个部门的员工人数，并按部门ID排序
SELECT department_id, COUNT(*) AS employee_count
FROM employees
GROUP BY department_id
ORDER BY department_id ASC;

-- 测试用例 2: 统计每个部门平均工资，并按部门ID排序
SELECT department_id, AVG(salary) AS avg_salary
FROM employees
GROUP BY department_id
ORDER BY department_id ASC;

-- 测试用例3：涉及外键的级联更新
UPDATE departments SET dept_id=5 WHERE dept_id=2;

-- 测试用例4：多表查询
SELECT e.name,e.salary,d.dept_name
FROM employees e
JOIN departments d ON d.dept_id =e.department_id;
