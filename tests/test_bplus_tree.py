# tests/test_bplus_tree.py
import os
import shutil
import unittest
import random
from storage.page import PageManager
from storage.buffer import BufferPool
from storage.bplus_tree import BPlusTree


class TestBPlusTree(unittest.TestCase):
    """测试基于 4KB Page 的 B+ 树索引实现"""

    def setUp(self):
        self.test_dir = "test_data_bpt"
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        os.makedirs(self.test_dir, exist_ok=True)

        self.pm = PageManager(self.test_dir)
        self.bp = BufferPool(self.pm, pool_size=50)
        # 使用较小的 max_keys=8 使得少量数据即可触发深层节点分裂
        self.bpt = BPlusTree.create(self.bp, max_keys=8)

    def tearDown(self):
        self.pm.close()
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_01_simple_insert_and_search(self):
        # 简单插入
        self.bpt.insert(10, page_id=1, slot_id=0)
        self.bpt.insert(20, page_id=1, slot_id=1)
        self.bpt.insert(5, page_id=1, slot_id=2)

        # 点查
        r10 = self.bpt.search(10)
        self.assertEqual(r10, [(1, 0)])

        r5 = self.bpt.search(5)
        self.assertEqual(r5, [(1, 2)])

        r999 = self.bpt.search(999)
        self.assertEqual(r999, [])

    def test_02_massive_insert_with_splits(self):
        # 插入 150 个乱序数字，触发多层分裂（max_keys=8）
        nums = list(range(1, 151))
        random.seed(42)
        random.shuffle(nums)

        for n in nums:
            self.bpt.insert(n, page_id=n // 10, slot_id=n % 10)

        # 验证所有 150 个数字均能 100% 精确检索
        for n in range(1, 151):
            res = self.bpt.search(n)
            self.assertEqual(len(res), 1, f"Failed searching for {n}")
            self.assertEqual(res[0], (n // 10, n % 10))

    def test_03_range_scan(self):
        # 插入有序数据
        for i in range(1, 101):
            self.bpt.insert(i, page_id=10, slot_id=i)

        # 范围查询 [30, 40]
        results = self.bpt.range_scan(low_key=30, high_key=40)
        keys_found = [k for k, rid in results]
        expected = list(range(30, 41))
        self.assertEqual(keys_found, expected)

    def test_04_delete(self):
        self.bpt.insert(100, 1, 1)
        self.bpt.insert(200, 1, 2)
        self.assertEqual(len(self.bpt.search(100)), 1)

        ok = self.bpt.delete(100, 1, 1)
        self.assertTrue(ok)
        self.assertEqual(self.bpt.search(100), [])
        self.assertEqual(len(self.bpt.search(200)), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
