# tests/test_database.py
import os
import shutil
import unittest
from engine.database import DataSphereDB, ExecutionResult
from utils.helpers import format_output, display_width


class TestDataSphereDBFacade(unittest.TestCase):
    """测试 DataSphereDB 门面类的程序化 API 接口"""

    @classmethod
    def setUpClass(cls):
        cls.test_dir = "test_data_facade"
        if os.path.exists(cls.test_dir):
            shutil.rmtree(cls.test_dir)
        cls.db = DataSphereDB(data_dir=cls.test_dir)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        if os.path.exists(cls.test_dir):
            shutil.rmtree(cls.test_dir)

    def test_01_create_table_and_validate(self):
        # 测试在未建表前，validate 是否通过
        val_res = self.db.validate("CREATE TABLE students (id INT PRIMARY KEY, name VARCHAR(20), age INT);")
        self.assertTrue(val_res.success)
        self.assertIn("Validation successful", val_res.message)

        # 实际执行建表
        exec_res = self.db.execute("CREATE TABLE students (id INT PRIMARY KEY, name VARCHAR(20), age INT);")
        self.assertTrue(exec_res.success)
        self.assertIn("students", exec_res.message)

        # 重复建表应返回失败但捕获错误
        dup_res = self.db.execute("CREATE TABLE students (id INT);")
        self.assertFalse(dup_res.success)
        self.assertTrue("already exists" in dup_res.error or "已存在" in dup_res.error)

    def test_02_insert_and_select(self):
        # 插入多条记录
        r1 = self.db.execute("INSERT INTO students(id, name, age) VALUES (1, '张三', 20);")
        self.assertTrue(r1.success)
        self.assertEqual(r1.row_count, 1)

        r2 = self.db.execute("INSERT INTO students(id, name, age) VALUES (2, '李四', 22);")
        self.assertTrue(r2.success)

        # 查询
        q = self.db.execute("SELECT * FROM students;")
        self.assertTrue(q.success)
        self.assertEqual(q.row_count, 2)
        self.assertIsNotNone(q.data)
        self.assertEqual(q.data[0]["name"], "张三")

    def test_03_schema_summary(self):
        summary = self.db.get_schema_summary()
        self.assertIn("students", summary)
        self.assertIn("PRIMARY KEY", summary)
        self.assertIn("VARCHAR", summary)

        catalog_dict = self.db.get_catalog_dict()
        self.assertIn("students", catalog_dict)
        self.assertEqual(catalog_dict["students"]["primary_key"], "id")

    def test_04_chinese_table_formatting(self):
        # 验证表格格式化对中文字符的宽度计算
        self.assertEqual(display_width("张三"), 4)
        self.assertEqual(display_width("Bob"), 3)

        rows = [
            {"id": 1, "姓名": "张三", "age": 20},
            {"id": 2, "姓名": "李四丰", "age": 22},
        ]
        table_text = format_output(rows)
        self.assertIn("张三", table_text)
        self.assertIn("李四丰", table_text)
        self.assertIn("2 row(s) returned", table_text)

    def test_05_error_smart_hints(self):
        # 测试外键违反错误提取智能提示
        self.db.execute("CREATE TABLE courses (cid INT, sid INT, FOREIGN KEY (sid) REFERENCES students(id));")
        res = self.db.execute("INSERT INTO courses(cid, sid) VALUES (101, 999);")
        self.assertFalse(res.success)
        self.assertEqual(res.error_type, "ConstraintViolationError")
        self.assertTrue(len(res.smart_hints) > 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
