# tests/test_index_scan.py
import os
import shutil
import unittest
from engine.database import DataSphereDB


class TestIndexScan(unittest.TestCase):
    def setUp(self):
        self.test_dir = 'test_idx_db'
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        os.makedirs(self.test_dir, exist_ok=True)
        self.db = DataSphereDB(data_dir=self.test_dir)

    def tearDown(self):
        self.db.close()
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_auto_pk_index_creation_and_point_query(self):
        # 1. 创建带主键的表
        sql_create = "CREATE TABLE users (id INT, name VARCHAR(20), age INT, PRIMARY KEY(id));"
        res_create = self.db.execute(sql_create)
        self.assertTrue(res_create.success)

        # 验证 FileManager 已为 users.id 创建 B+ 树
        tree = self.db.file_manager.get_bplus_tree("users", "id")
        self.assertIsNotNone(tree, "B+ Tree index on users.id should be automatically created")

        # 2. 插入多条记录
        for i in range(1, 31):
            res_ins = self.db.execute(f"INSERT INTO users (id, name, age) VALUES ({i}, 'User_{i}', {20 + i});")
            self.assertTrue(res_ins.success)

        # 验证 B+ 树内部条目数
        self.assertEqual(len(tree.range_scan(None, None)), 30)

        # 3. 点查：WHERE id = 15
        res = self.db.execute("SELECT id, name, age FROM users WHERE id = 15;")
        self.assertTrue(res.success)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]["id"], 15)
        self.assertEqual(res.data[0]["name"], "User_15")
        self.assertEqual(res.data[0]["age"], 35)

        # 4. 点查不存在的键：WHERE id = 999
        res_none = self.db.execute("SELECT id, name, age FROM users WHERE id = 999;")
        self.assertTrue(res_none.success)
        self.assertEqual(len(res_none.data), 0)

    def test_range_query_via_index(self):
        self.db.execute("CREATE TABLE products (id INT, price INT, PRIMARY KEY(id));")
        for i in range(1, 21):
            self.db.execute(f"INSERT INTO products (id, price) VALUES ({i}, {i * 10});")

        # > 15 -> 16..20 (5 rows)
        res_gt = self.db.execute("SELECT id, price FROM products WHERE id > 15;")
        self.assertTrue(res_gt.success)
        self.assertEqual(len(res_gt.data), 5)
        self.assertEqual([r["id"] for r in res_gt.data], [16, 17, 18, 19, 20])

        # <= 5 -> 1..5 (5 rows)
        res_le = self.db.execute("SELECT id, price FROM products WHERE id <= 5;")
        self.assertTrue(res_le.success)
        self.assertEqual(len(res_le.data), 5)
        self.assertEqual([r["id"] for r in res_le.data], [1, 2, 3, 4, 5])

    def test_pk_duplicate_rejection_via_index(self):
        self.db.execute("CREATE TABLE accounts (acc_id INT, balance INT, PRIMARY KEY(acc_id));")
        res1 = self.db.execute("INSERT INTO accounts (acc_id, balance) VALUES (101, 500);")
        self.assertTrue(res1.success)

        res2 = self.db.execute("INSERT INTO accounts (acc_id, balance) VALUES (101, 800);")
        self.assertFalse(res2.success)
        self.assertIn("Primary key violation", res2.error)

    def test_manual_index_creation_and_rebuild(self):
        self.db.execute("CREATE TABLE items (id INT, code VARCHAR(10));")
        self.db.execute("INSERT INTO items (id, code) VALUES (1, 'A1');")
        self.db.execute("INSERT INTO items (id, code) VALUES (2, 'B2');")

        # 手动为 code 创建索引（此时表中已有数据，验证能否自动回填数据）
        idx = self.db.file_manager.create_index("items", "code")
        self.assertIsNotNone(idx)
        self.assertEqual(len(idx.range_scan(None, None)), 2)

        # 点查 code = 'B2'
        res = self.db.execute("SELECT id, code FROM items WHERE code = 'B2';")
        self.assertTrue(res.success)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]["id"], 2)


if __name__ == '__main__':
    unittest.main()
