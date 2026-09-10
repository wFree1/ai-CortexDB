-- 建表测试
CREATE TABLE student(
  id   INT PRIMARY KEY,
  name VARCHAR(20),
  age  INT
);

CREATE TABLE class(
  sid  INT,
  name VARCHAR,
  PRIMARY KEY(sid)
);

CREATE TABLE dept(
  id     INT PRIMARY KEY,
  dname  VARCHAR(8)
);

-- 插入测试
INSERT INTO student(id, name, age) VALUES (1, 'Alice', 20);
INSERT INTO student(id, name, age) VALUES (2, 'Bob',   21);
INSERT INTO student(id, name, age) VALUES (3, 'Cindy', 20);

INSERT INTO class(sid, name) VALUES (1, 'CS101');
INSERT INTO class(sid, name) VALUES (2, 'CS102');
INSERT INTO class(sid, name) VALUES (3, 'CS101');

-- 查询测试
SELECT id, name FROM student WHERE age > 18 ORDER BY name;

-- 删除测试
DELETE FROM student WHERE id = 1;

-- 更新测试
UPDATE student SET age = 21, name = 'Bob' WHERE id = 3;

-- JOIN 测试
SELECT s.id, s.name FROM student s JOIN class c ON s.id = c.sid;

-- GROUP BY 测试
SELECT age FROM student GROUP BY age;

SELECT s.age FROM student s JOIN class c ON s.id = c.sid GROUP BY age;

-- ORDER BY 测试
SELECT id, name FROM student ORDER BY name ASC;
SELECT id, age FROM student WHERE age > 18 ORDER BY age DESC;

-- 谓词下推测试
SELECT s.id, s.name
FROM student s JOIN class c ON s.id = c.sid
WHERE s.age > 18 AND c.name = 'CS101';
