# tests/test_rich_types.py
import os
import shutil
import unittest
from engine.database import DataSphereDB


class TestRichTypes(unittest.TestCase):
    def setUp(self):
        self.test_dir = 'test_types_db'
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        os.makedirs(self.test_dir, exist_ok=True)
        self.db = DataSphereDB(data_dir=self.test_dir)

    def tearDown(self):
        self.db.close()
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_integers_and_floats(self):
        # BIGINT, SMALLINT, TINYINT, DOUBLE, DECIMAL
        res = self.db.execute("""
            CREATE TABLE num_test (
                id BIGINT,
                s_val SMALLINT,
                t_val TINYINT,
                d_val DOUBLE,
                dec_val DECIMAL,
                PRIMARY KEY (id)
            );
        """)
        self.assertTrue(res.success)

        res_ins = self.db.execute("""
            INSERT INTO num_test (id, s_val, t_val, d_val, dec_val)
            VALUES (922337203685477580, 32000, 120, 3.1415926535, 999.99);
        """)
        self.assertTrue(res_ins.success)

        res_sel = self.db.execute("SELECT id, s_val, t_val, d_val, dec_val FROM num_test WHERE id = 922337203685477580;")
        self.assertTrue(res_sel.success)
        self.assertEqual(len(res_sel.data), 1)
        row = res_sel.data[0]
        self.assertEqual(row['id'], 922337203685477580)
        self.assertEqual(row['s_val'], 32000)
        self.assertEqual(row['t_val'], 120)
        self.assertAlmostEqual(row['d_val'], 3.1415926535, places=6)
        self.assertEqual(row['dec_val'], 999.99)

    def test_dates_and_datetimes(self):
        res = self.db.execute("""
            CREATE TABLE event_test (
                id INT,
                event_date DATE,
                created_at DATETIME,
                PRIMARY KEY (id)
            );
        """)
        self.assertTrue(res.success)

        res_ins = self.db.execute("""
            INSERT INTO event_test (id, event_date, created_at)
            VALUES (1, '2026-09-11', '2026-09-11 12:30:00');
        """)
        self.assertTrue(res_ins.success)

        res_sel = self.db.execute("SELECT event_date, created_at FROM event_test WHERE id = 1;")
        self.assertTrue(res_sel.success)
        self.assertEqual(len(res_sel.data), 1)
        self.assertEqual(res_sel.data[0]['event_date'], '2026-09-11')
        self.assertEqual(res_sel.data[0]['created_at'], '2026-09-11 12:30:00')

    def test_null_support_and_is_null_predicate(self):
        res = self.db.execute("""
            CREATE TABLE null_test (
                id INT,
                name VARCHAR(50),
                score DOUBLE,
                PRIMARY KEY (id)
            );
        """)
        self.assertTrue(res.success)

        # 插入包含 NULL 的记录
        self.db.execute("INSERT INTO null_test (id, name, score) VALUES (1, 'Alice', 95.5);")
        self.db.execute("INSERT INTO null_test (id, name, score) VALUES (2, NULL, 80.0);")
        self.db.execute("INSERT INTO null_test (id, name, score) VALUES (3, 'Charlie', NULL);")

        # 测试 IS NULL
        res_null_name = self.db.execute("SELECT id FROM null_test WHERE name IS NULL;")
        self.assertTrue(res_null_name.success)
        self.assertEqual(len(res_null_name.data), 1)
        self.assertEqual(res_null_name.data[0]['id'], 2)

        # 测试 IS NOT NULL
        res_not_null = self.db.execute("SELECT id FROM null_test WHERE score IS NOT NULL;")
        self.assertTrue(res_not_null.success)
        self.assertEqual(len(res_not_null.data), 2)
        ids = [r['id'] for r in res_not_null.data]
        self.assertIn(1, ids)
        self.assertIn(2, ids)

    def test_text_and_bool_types(self):
        res = self.db.execute("""
            CREATE TABLE text_bool_test (
                id INT,
                is_active BOOL,
                bio TEXT,
                PRIMARY KEY (id)
            );
        """)
        self.assertTrue(res.success)

        self.db.execute("INSERT INTO text_bool_test (id, is_active, bio) VALUES (1, TRUE, 'A long bio for test user');")
        self.db.execute("INSERT INTO text_bool_test (id, is_active, bio) VALUES (2, FALSE, 'Another description');")

        res_sel = self.db.execute("SELECT id, is_active, bio FROM text_bool_test WHERE is_active = TRUE;")
        self.assertTrue(res_sel.success)
        self.assertEqual(len(res_sel.data), 1)
        self.assertEqual(res_sel.data[0]['id'], 1)
        self.assertEqual(res_sel.data[0]['bio'], 'A long bio for test user')


if __name__ == '__main__':
    unittest.main()
