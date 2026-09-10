# tests/test_advanced_sql.py
import os
import shutil
import unittest
from engine.database import DataSphereDB


class TestAdvancedSQL(unittest.TestCase):
    def setUp(self):
        self.test_dir = 'test_adv_db'
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        os.makedirs(self.test_dir, exist_ok=True)
        self.db = DataSphereDB(data_dir=self.test_dir)

    def tearDown(self):
        self.db.close()
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_show_tables_and_describe(self):
        self.db.execute("CREATE TABLE users (id INT, name VARCHAR(50), PRIMARY KEY (id));")
        self.db.execute("CREATE TABLE orders (order_id INT, amount DOUBLE, PRIMARY KEY (order_id));")

        # SHOW TABLES
        res_tables = self.db.execute("SHOW TABLES;")
        self.assertTrue(res_tables.success)
        names = [r['table_name'] for r in res_tables.data]
        self.assertIn('users', names)
        self.assertIn('orders', names)

        # DESCRIBE / DESC
        res_desc = self.db.execute("DESCRIBE users;")
        self.assertTrue(res_desc.success)
        cols = {r['column_name']: r['type'] for r in res_desc.data}
        self.assertIn('id', cols)
        self.assertIn('name', cols)

    def test_drop_and_truncate_table(self):
        self.db.execute("CREATE TABLE temp_tbl (id INT, val VARCHAR(20), PRIMARY KEY (id));")
        self.db.execute("INSERT INTO temp_tbl (id, val) VALUES (1, 'alpha');")
        self.db.execute("INSERT INTO temp_tbl (id, val) VALUES (2, 'beta');")

        # TRUNCATE
        res_trunc = self.db.execute("TRUNCATE TABLE temp_tbl;")
        self.assertTrue(res_trunc.success)
        res_sel = self.db.execute("SELECT * FROM temp_tbl;")
        self.assertEqual(len(res_sel.data), 0)

        # DROP TABLE
        res_drop = self.db.execute("DROP TABLE temp_tbl;")
        self.assertTrue(res_drop.success)

        # DROP TABLE IF EXISTS (should succeed gracefully)
        res_drop_ie = self.db.execute("DROP TABLE IF EXISTS temp_tbl;")
        self.assertTrue(res_drop_ie.success)

    def test_alter_table_add_and_drop_column(self):
        self.db.execute("CREATE TABLE employees (id INT, name VARCHAR(50), PRIMARY KEY (id));")
        self.db.execute("INSERT INTO employees (id, name) VALUES (1, 'Alice');")

        # ALTER TABLE ADD COLUMN
        res_add = self.db.execute("ALTER TABLE employees ADD COLUMN department VARCHAR(50);")
        self.assertTrue(res_add.success)

        res_sel = self.db.execute("SELECT id, name, department FROM employees;")
        self.assertTrue(res_sel.success)
        self.assertEqual(len(res_sel.data), 1)
        self.assertIsNone(res_sel.data[0]['department'])

        # Update the new column
        self.db.execute("UPDATE employees SET department = 'Engineering' WHERE id = 1;")
        res_sel2 = self.db.execute("SELECT department FROM employees WHERE id = 1;")
        self.assertEqual(res_sel2.data[0]['department'], 'Engineering')

        # ALTER TABLE DROP COLUMN
        res_drop_col = self.db.execute("ALTER TABLE employees DROP COLUMN department;")
        self.assertTrue(res_drop_col.success)
        res_sel3 = self.db.execute("SELECT * FROM employees WHERE id = 1;")
        self.assertNotIn('department', res_sel3.data[0])

    def test_index_ddl(self):
        self.db.execute("CREATE TABLE indexed_tbl (id INT, code VARCHAR(30), PRIMARY KEY (id));")
        self.db.execute("INSERT INTO indexed_tbl (id, code) VALUES (1, 'CODE_A');")

        # CREATE INDEX
        res_idx = self.db.execute("CREATE INDEX idx_code ON indexed_tbl(code);")
        self.assertTrue(res_idx.success)

        # DROP INDEX
        res_drop_idx = self.db.execute("DROP INDEX idx_code;")
        self.assertTrue(res_drop_idx.success)

    def test_distinct_and_limit_offset(self):
        self.db.execute("CREATE TABLE products (id INT, category VARCHAR(30), price DOUBLE, PRIMARY KEY (id));")
        self.db.execute("INSERT INTO products (id, category, price) VALUES (1, 'Books', 10.0);")
        self.db.execute("INSERT INTO products (id, category, price) VALUES (2, 'Books', 15.0);")
        self.db.execute("INSERT INTO products (id, category, price) VALUES (3, 'Electronics', 100.0);")
        self.db.execute("INSERT INTO products (id, category, price) VALUES (4, 'Electronics', 200.0);")
        self.db.execute("INSERT INTO products (id, category, price) VALUES (5, 'Clothing', 50.0);")

        # DISTINCT
        res_dist = self.db.execute("SELECT DISTINCT category FROM products;")
        self.assertTrue(res_dist.success)
        cats = [r['category'] for r in res_dist.data]
        self.assertEqual(len(cats), 3)
        self.assertEqual(sorted(cats), ['Books', 'Clothing', 'Electronics'])

        # LIMIT
        res_lim = self.db.execute("SELECT id FROM products ORDER BY id ASC LIMIT 2;")
        self.assertTrue(res_lim.success)
        self.assertEqual(len(res_lim.data), 2)
        self.assertEqual([r['id'] for r in res_lim.data], [1, 2])

        # LIMIT with OFFSET
        res_off = self.db.execute("SELECT id FROM products ORDER BY id ASC LIMIT 2 OFFSET 2;")
        self.assertTrue(res_off.success)
        self.assertEqual(len(res_off.data), 2)
        self.assertEqual([r['id'] for r in res_off.data], [3, 4])

    def test_rich_where_predicates(self):
        self.db.execute("CREATE TABLE items (id INT, name VARCHAR(50), status VARCHAR(20), price INT, PRIMARY KEY (id));")
        self.db.execute("INSERT INTO items (id, name, status, price) VALUES (1, 'Laptop Pro', 'available', 1500);")
        self.db.execute("INSERT INTO items (id, name, status, price) VALUES (2, 'Desktop PC', 'sold', 800);")
        self.db.execute("INSERT INTO items (id, name, status, price) VALUES (3, 'Laptop Air', 'pending', 1200);")
        self.db.execute("INSERT INTO items (id, name, status, price) VALUES (4, 'Wireless Mouse', 'available', 50);")

        # LIKE
        res_like = self.db.execute("SELECT id FROM items WHERE name LIKE 'Laptop%';")
        self.assertTrue(res_like.success)
        self.assertEqual(len(res_like.data), 2)
        self.assertEqual(sorted([r['id'] for r in res_like.data]), [1, 3])

        # NOT LIKE
        res_not_like = self.db.execute("SELECT id FROM items WHERE name NOT LIKE 'Laptop%';")
        self.assertTrue(res_not_like.success)
        self.assertEqual(sorted([r['id'] for r in res_not_like.data]), [2, 4])

        # IN
        res_in = self.db.execute("SELECT id FROM items WHERE status IN ('available', 'pending');")
        self.assertTrue(res_in.success)
        self.assertEqual(sorted([r['id'] for r in res_in.data]), [1, 3, 4])

        # NOT IN
        res_not_in = self.db.execute("SELECT id FROM items WHERE status NOT IN ('sold', 'pending');")
        self.assertTrue(res_not_in.success)
        self.assertEqual(sorted([r['id'] for r in res_not_in.data]), [1, 4])

        # BETWEEN ... AND ...
        res_btwn = self.db.execute("SELECT id FROM items WHERE price BETWEEN 800 AND 1300;")
        self.assertTrue(res_btwn.success)
        self.assertEqual(sorted([r['id'] for r in res_btwn.data]), [2, 3])

        # NOT BETWEEN
        res_not_btwn = self.db.execute("SELECT id FROM items WHERE price NOT BETWEEN 800 AND 1300;")
        self.assertTrue(res_not_btwn.success)
        self.assertEqual(sorted([r['id'] for r in res_not_btwn.data]), [1, 4])

        # Complex AND / OR
        res_and_or = self.db.execute("SELECT id FROM items WHERE (status = 'available' AND price > 100) OR id = 2;")
        self.assertTrue(res_and_or.success)
        self.assertEqual(sorted([r['id'] for r in res_and_or.data]), [1, 2])

    def test_max_min_and_having(self):
        self.db.execute("CREATE TABLE sales (id INT, dept VARCHAR(20), amount INT, PRIMARY KEY (id));")
        self.db.execute("INSERT INTO sales (id, dept, amount) VALUES (1, 'IT', 500);")
        self.db.execute("INSERT INTO sales (id, dept, amount) VALUES (2, 'IT', 1500);")
        self.db.execute("INSERT INTO sales (id, dept, amount) VALUES (3, 'HR', 300);")
        self.db.execute("INSERT INTO sales (id, dept, amount) VALUES (4, 'HR', 700);")

        # MAX and MIN
        res_max_min = self.db.execute("SELECT MAX(amount) AS max_amt, MIN(amount) AS min_amt FROM sales;")
        self.assertTrue(res_max_min.success)
        self.assertEqual(res_max_min.data[0]['max_amt'], 1500)
        self.assertEqual(res_max_min.data[0]['min_amt'], 300)

        # GROUP BY with HAVING
        res_having = self.db.execute("SELECT dept, SUM(amount) AS total FROM sales GROUP BY dept HAVING total > 1500;")
        self.assertTrue(res_having.success)
        self.assertEqual(len(res_having.data), 1)
        self.assertEqual(res_having.data[0]['dept'], 'IT')
        self.assertEqual(res_having.data[0]['total'], 2000)

    def test_scalar_functions(self):
        self.db.execute("CREATE TABLE scalars (id INT, name VARCHAR(20), num DOUBLE, PRIMARY KEY (id));")
        self.db.execute("INSERT INTO scalars (id, name, num) VALUES (1, 'Antigravity', -42.75);")

        res = self.db.execute("SELECT UPPER(name) AS u_name, LOWER(name) AS l_name, LENGTH(name) AS n_len, ABS(num) AS a_num, ROUND(num) AS r_num FROM scalars WHERE id = 1;")
        self.assertTrue(res.success)
        row = res.data[0]
        self.assertEqual(row['u_name'], 'ANTIGRAVITY')
        self.assertEqual(row['l_name'], 'antigravity')
        self.assertEqual(row['n_len'], 11)
        self.assertAlmostEqual(row['a_num'], 42.75)
        self.assertEqual(row['r_num'], -43.0)

    def test_joins_types(self):
        self.db.execute("CREATE TABLE depts (dept_id INT, dname VARCHAR(30), PRIMARY KEY (dept_id));")
        self.db.execute("CREATE TABLE emps (emp_id INT, ename VARCHAR(30), dept_id INT, PRIMARY KEY (emp_id));")

        self.db.execute("INSERT INTO depts (dept_id, dname) VALUES (10, 'Engineering');")
        self.db.execute("INSERT INTO depts (dept_id, dname) VALUES (20, 'Marketing');")
        self.db.execute("INSERT INTO depts (dept_id, dname) VALUES (30, 'Finance');")

        self.db.execute("INSERT INTO emps (emp_id, ename, dept_id) VALUES (1, 'Alice', 10);")
        self.db.execute("INSERT INTO emps (emp_id, ename, dept_id) VALUES (2, 'Bob', 20);")
        self.db.execute("INSERT INTO emps (emp_id, ename, dept_id) VALUES (3, 'Charlie', 99);")  # No matching dept

        # LEFT JOIN
        res_left = self.db.execute("SELECT emps.ename, depts.dname FROM emps LEFT JOIN depts ON emps.dept_id = depts.dept_id ORDER BY emps.emp_id ASC;")
        self.assertTrue(res_left.success)
        self.assertEqual(len(res_left.data), 3)
        self.assertEqual(res_left.data[0]['depts.dname'], 'Engineering')
        self.assertIsNone(res_left.data[2]['depts.dname'])

        # RIGHT JOIN
        res_right = self.db.execute("SELECT emps.ename, depts.dname FROM emps RIGHT JOIN depts ON emps.dept_id = depts.dept_id ORDER BY depts.dept_id ASC;")
        self.assertTrue(res_right.success)
        self.assertEqual(len(res_right.data), 3)
        names = [r['depts.dname'] for r in res_right.data]
        self.assertEqual(sorted(names), ['Engineering', 'Finance', 'Marketing'])
        # Finance has no emp
        finance_row = [r for r in res_right.data if r['depts.dname'] == 'Finance'][0]
        self.assertIsNone(finance_row['emps.ename'])

        # CROSS JOIN
        res_cross = self.db.execute("SELECT emps.emp_id, depts.dept_id FROM emps CROSS JOIN depts;")
        self.assertTrue(res_cross.success)
        self.assertEqual(len(res_cross.data), 9)  # 3 * 3 = 9 rows

    def test_delete_and_update_with_rich_predicates(self):
        self.db.execute("CREATE TABLE tasks (id INT, title VARCHAR(50), priority INT, PRIMARY KEY (id));")
        self.db.execute("INSERT INTO tasks (id, title, priority) VALUES (1, 'Fix bug', 1);")
        self.db.execute("INSERT INTO tasks (id, title, priority) VALUES (2, 'Write docs', 2);")
        self.db.execute("INSERT INTO tasks (id, title, priority) VALUES (3, 'Release v1', 3);")
        self.db.execute("INSERT INTO tasks (id, title, priority) VALUES (4, 'Deploy cloud', 4);")

        # UPDATE with BETWEEN
        res_up = self.db.execute("UPDATE tasks SET priority = 10 WHERE priority BETWEEN 2 AND 3;")
        self.assertTrue(res_up.success)

        res_chk = self.db.execute("SELECT id, priority FROM tasks WHERE priority = 10;")
        self.assertEqual(len(res_chk.data), 2)
        self.assertEqual(sorted([r['id'] for r in res_chk.data]), [2, 3])

        # DELETE with IN
        res_del = self.db.execute("DELETE FROM tasks WHERE id IN (1, 4);")
        self.assertTrue(res_del.success)

        res_remain = self.db.execute("SELECT id FROM tasks;")
        self.assertEqual(len(res_remain.data), 2)
        self.assertEqual(sorted([r['id'] for r in res_remain.data]), [2, 3])


if __name__ == '__main__':
    unittest.main()
