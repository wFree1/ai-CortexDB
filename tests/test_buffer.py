import unittest
from unittest.mock import MagicMock, patch, call
import sys
import os

# --- 设置模块导入路径 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
# 获取项目根目录 (tests 的父目录)
project_root = os.path.dirname(current_dir)
# 将项目根目录添加到 sys.path 开头
sys.path.insert(0, project_root)

from storage.buffer import BufferPool
from storage.page import Page, PageManager

class TestBufferPool(unittest.TestCase):

    def setUp(self):
        """
        在每个测试方法运行前执行。
        设置 Mock 对象和 BufferPool 实例。
        """
        # Mock PageManager 以避免真实的文件 I/O 操作
        self.mock_page_manager = MagicMock(spec=PageManager)
        self.pool_size = 3  # 使用较小的池大小方便测试

        # 创建 BufferPool 实例用于测试  (默认 LRU)
        self.bp_lru = BufferPool(self.mock_page_manager, pool_size=self.pool_size, policy='LRU')
        # 创建 BufferPool 实例用于测试 (FIFO)
        self.bp_fifo = BufferPool(self.mock_page_manager, pool_size=self.pool_size, policy='FIFO')

        # 创建一些 Mock Page 对象用于测试
        self.mock_pages = {}
        for i in range(10): # 创建足够多的页用于测试
            # 使用 MagicMock 并显式设置属性，避免 spec 的潜在限制和属性访问问题
            page = MagicMock()
            page.page_id = i
            # 显式设置 is_dirty 属性为 False，确保默认状态
            # 这样在测试中赋值 True 时，行为更可预测
            page.is_dirty = False
            self.mock_pages[i] = page

        # 配置 PageManager 的 read_page 方法返回对应的 Mock Page
        def side_effect_read_page(page_id):
            return self.mock_pages.get(page_id)
        self.mock_page_manager.read_page.side_effect = side_effect_read_page

    def test_initialization(self):
        """测试 BufferPool 初始化"""
        self.assertEqual(self.bp_lru.pool_size, self.pool_size)
        self.assertEqual(self.bp_lru.policy, 'LRU')
        self.assertEqual(len(self.bp_lru.buffer), 0)
        self.assertEqual(self.bp_lru.hit_count, 0)
        self.assertEqual(self.bp_lru.miss_count, 0)

        self.assertEqual(self.bp_fifo.policy, 'FIFO')

        # 测试不支持的策略
        with self.assertRaises(ValueError):
            BufferPool(self.mock_page_manager, policy='INVALID')

    def test_get_page_miss(self):
        """测试 get_page 未命中情况"""
        page_id = 1
        # 确保 Mock PageManager 返回 Mock Page
        self.mock_page_manager.read_page.return_value = self.mock_pages[page_id]

        # 调用 get_page
        result_page = self.bp_lru.get_page(page_id)

        # 验证结果
        self.assertEqual(result_page, self.mock_pages[page_id])
        self.assertIn(page_id, self.bp_lru.buffer)
        self.assertEqual(self.bp_lru.hit_count, 0)
        self.assertEqual(self.bp_lru.miss_count, 1)
        # 验证 PageManager.read_page 被调用
        self.mock_page_manager.read_page.assert_called_once_with(page_id)

    def test_get_page_hit_lru(self):
        """测试 get_page 命中情况 (LRU)"""
        page_id = 1
        # 先放入缓存 (模拟之前访问过)
        self.bp_lru.buffer[page_id] = self.mock_pages[page_id]

        # 调用 get_page
        result_page = self.bp_lru.get_page(page_id)

        # 验证结果
        self.assertEqual(result_page, self.mock_pages[page_id])
        # 对于 LRU，命中后应移动到末尾 (最近使用)
        # OrderedDict 的顺序可以通过 list(keys()) 检查
        self.assertEqual(list(self.bp_lru.buffer.keys())[-1], page_id) # 应该是最后一个
        self.assertEqual(self.bp_lru.hit_count, 1)
        self.assertEqual(self.bp_lru.miss_count, 0)
        # 命中不应调用 PageManager.read_page
        self.mock_page_manager.read_page.assert_not_called()

    def test_get_page_hit_fifo(self):
        """测试 get_page 命中情况 (FIFO)"""
        page_id_1, page_id_2 = 1, 2
        # 先放入缓存 (模拟之前访问过)
        self.bp_fifo.buffer[page_id_1] = self.mock_pages[page_id_1]
        self.bp_fifo.buffer[page_id_2] = self.mock_pages[page_id_2]
        # 初始顺序应为 [page_id_1, page_id_2]

        # 访问 page_id_1 (命中)
        result_page = self.bp_fifo.get_page(page_id_1)

        # 验证结果
        self.assertEqual(result_page, self.mock_pages[page_id_1])
        # 对于 FIFO，命中后顺序不应改变
        self.assertEqual(list(self.bp_fifo.buffer.keys()), [page_id_1, page_id_2])
        self.assertEqual(self.bp_fifo.hit_count, 1)
        self.assertEqual(self.bp_fifo.miss_count, 0)
        # 命中不应调用 PageManager.read_page
        self.mock_page_manager.read_page.assert_not_called()

    def test_lru_policy_eviction(self):
        """测试 LRU 策略的驱逐逻辑"""
        # 1. 加载页 0 和 1 到缓存 (缓存大小 2 < pool_size 3)
        page0 = self.bp_lru.get_page(0)
        page1 = self.bp_lru.get_page(1)
        self.assertIsNotNone(page0)
        self.assertIsNotNone(page1)
        self.assertIn(0, self.bp_lru.buffer)
        self.assertIn(1, self.bp_lru.buffer)
        self.assertEqual(len(self.bp_lru.buffer), 2)  # 确认加载了两个

        # 2. 再次访问 page 0 (命中，使其变为最近使用，LRU 顺序变为 [1, 0])
        self.bp_lru.get_page(0)  # Hit
        self.assertEqual(list(self.bp_lru.buffer.keys())[-1], 0)  # 0 应该在末尾 (MRU)

        # 3. 加载页 2 (未命中，缓存将变为 [1, 0, 2]，大小为 3)
        page2 = self.bp_lru.get_page(2)
        self.assertIsNotNone(page2)
        self.assertIn(2, self.bp_lru.buffer)
        self.assertEqual(len(self.bp_lru.buffer), 3)  # 此时刚好满
        self.assertEqual(list(self.bp_lru.buffer.keys()), [1, 0, 2])  # 检查 LRU 顺序

        # 4. 加载新页 3 (未命中，缓存满，需要驱逐)
        #    根据 LRU，页 1 是最久未使用的 (LRU 顺序 [1, 0, 2] -> 驱逐 1)
        #    驱逐后，缓存应为 [0, 2, 3]
        page3 = self.bp_lru.get_page(3)
        self.assertIsNotNone(page3)

        # 5. 检查最终状态
        self.assertEqual(len(self.bp_lru.buffer), self.pool_size)  # 缓存大小应为 pool_size
        self.assertNotIn(1, self.bp_lru.buffer)  # page 1 应被驱逐 (LRU)
        self.assertIn(0, self.bp_lru.buffer)  # page 0 应仍在缓存
        self.assertIn(2, self.bp_lru.buffer)  # page 2 应仍在缓存
        self.assertIn(3, self.bp_lru.buffer)  # page 3 应被加入缓存
        self.assertEqual(list(self.bp_lru.buffer.keys()), [0, 2, 3])  # 检查最终 LRU 顺序
        # 验证 page 1 没有被写回 (因为它不是脏页)
        self.mock_page_manager.write_page.assert_not_called()

    def test_fifo_policy_eviction(self):
        """测试 FIFO 策略的驱逐逻辑"""
        # 1. 加载页 0 和 1 到缓存 (缓存大小 2 < pool_size 3)
        page0 = self.bp_fifo.get_page(0)
        page1 = self.bp_fifo.get_page(1)
        self.assertIsNotNone(page0)
        self.assertIsNotNone(page1)
        self.assertIn(0, self.bp_fifo.buffer)
        self.assertIn(1, self.bp_fifo.buffer)
        self.assertEqual(len(self.bp_fifo.buffer), 2)  # 确认加载了两个

        # 2. 访问页 0 (命中，FIFO 顺序不变 [0, 1])
        self.bp_fifo.get_page(0)  # Hit
        self.assertEqual(list(self.bp_fifo.buffer.keys()), [0, 1])  # 顺序应不变

        # 3. 加载页 2 (未命中，缓存将变为 [0, 1, 2]，大小为 3)
        page2 = self.bp_fifo.get_page(2)
        self.assertIsNotNone(page2)
        self.assertIn(2, self.bp_fifo.buffer)
        self.assertEqual(len(self.bp_fifo.buffer), 3)  # 此时刚好满
        self.assertEqual(list(self.bp_fifo.buffer.keys()), [0, 1, 2])  # 检查 FIFO 顺序

        # 4. 加载新页 3 (未命中，缓存满，需要驱逐)
        #    根据 FIFO，页 0 是最早进入的 (FIFO 顺序 [0, 1, 2] -> 驱逐 0)
        #    驱逐后，缓存应为 [1, 2, 3]
        page3 = self.bp_fifo.get_page(3)
        self.assertIsNotNone(page3)

        # 5. 检查最终状态
        self.assertEqual(len(self.bp_fifo.buffer), self.pool_size)  # 缓存大小应为 pool_size
        self.assertNotIn(0, self.bp_fifo.buffer)  # page 0 应被驱逐 (FIFO)
        self.assertIn(1, self.bp_fifo.buffer)  # page 1 应仍在缓存
        self.assertIn(2, self.bp_fifo.buffer)  # page 2 应仍在缓存
        self.assertIn(3, self.bp_fifo.buffer)  # page 3 应被加入缓存
        self.assertEqual(list(self.bp_fifo.buffer.keys()), [1, 2, 3])  # 检查最终 FIFO 顺序
        # 验证 page 0 没有被写回 (因为它不是脏页)
        self.mock_page_manager.write_page.assert_not_called()

    def test_dirty_page_flush_on_eviction_lru(self):
        """测试 LRU 驱逐脏页时是否刷新"""
        # 1. 加载页 0 和 1 到缓存
        page0 = self.bp_lru.get_page(0)
        page1 = self.bp_lru.get_page(1)
        self.assertIsNotNone(page0)
        self.assertIsNotNone(page1)

        # 2. 标记 page 0 为脏页
        page0.is_dirty = True
        # 更新 Mock 对象的状态以反映这一点（如果需要）
        self.mock_pages[0].is_dirty = True

        # 3. 访问页 2 (缓存满，触发驱逐)
        page2 = self.bp_lru.get_page(2)
        self.assertIsNotNone(page2)

        # 4. 再访问页 3 (缓存满，触发驱逐 page 1，因为它现在是 LRU)
        page3 = self.bp_lru.get_page(3)
        self.assertIsNotNone(page3)

        # 5. 再访问页 4 (缓存满，触发驱逐 page 0，因为它是脏页)
        page4 = self.bp_lru.get_page(4)
        self.assertIsNotNone(page4)

        # 6. 验证 PageManager.write_page 被调用了一次，且参数是 page 0
        self.mock_page_manager.write_page.assert_called_once_with(page0)
        # 验证 page 0 的 is_dirty 被重置 (在 _evict_page 内部)
        # 注意：直接检查 Mock 对象的属性可能不会反映方法内部的修改
        # 但我们知道 _evict_page 会设置 page.is_dirty = False
        # 更好的测试是验证 write_page 被调用后，如果 page 0 再次被驱逐，不会再次写入
        # 这里我们只验证第一次写入

    def test_dirty_page_flush_on_eviction_fifo(self):
        """测试 FIFO 驱逐脏页时是否刷新"""
        # 1. 加载页 0, 1, 2 到缓存 (刚好填满容量为3的缓存)
        page0 = self.bp_fifo.get_page(0)
        page1 = self.bp_fifo.get_page(1)
        page2 = self.bp_fifo.get_page(2) # 添加这一步
        self.assertIsNotNone(page0)
        self.assertIsNotNone(page1)
        self.assertIsNotNone(page2) # 添加这一步

        # 2. 标记 page 0 为脏页
        page0.is_dirty = True
        # 注意：page0 是 self.mock_pages[0] 的引用，所以这行是多余的，但保留以匹配 LRU 测试的风格
        self.mock_pages[0].is_dirty = True

        # 3. 加载新页 3 (缓存满，触发驱逐最早进入的页 page 0)
        page3 = self.bp_fifo.get_page(3) # 修改这里：加载页3而不是再次访问页1或页2
        self.assertIsNotNone(page3)

        # 5. 验证 PageManager.write_page 被调用了一次，且参数是 page 0
        # 现在，当加载 page3 时，缓存大小会超过容量，触发驱逐 page0 (脏页)，write_page 应该被调用。
        self.mock_page_manager.write_page.assert_called_once_with(page0)


    def test_flush_page(self):
        """测试 flush_page 功能"""
        page_id = 5
        # 先将页加载到缓存
        page = self.bp_lru.get_page(page_id)
        self.assertIsNotNone(page)

        # 标记为脏页
        page.is_dirty = True
        self.mock_pages[page_id].is_dirty = True

        # 调用 flush_page
        self.bp_lru.flush_page(page_id)

        # 验证 PageManager.write_page 被调用
        self.mock_page_manager.write_page.assert_called_once_with(page)
        # 验证页的 is_dirty 被设置为 False
        self.assertFalse(page.is_dirty)

    def test_flush_page_not_dirty(self):
        """测试 flush_page 对非脏页的处理"""
        page_id = 6
        # 先将页加载到缓存 (默认 is_dirty=False)
        page = self.bp_lru.get_page(page_id)
        self.assertIsNotNone(page)
        self.assertFalse(page.is_dirty)

        # 调用 flush_page
        self.bp_lru.flush_page(page_id)

        # 验证 PageManager.write_page 没有被调用
        self.mock_page_manager.write_page.assert_not_called()
        # 页的 is_dirty 应仍为 False
        self.assertFalse(page.is_dirty)

    def test_flush_page_not_in_buffer(self):
        """测试 flush_page 对不在缓存中的页的处理"""
        page_id = 999 # 一个不存在于缓存中的页ID
        # 调用 flush_page
        self.bp_lru.flush_page(page_id)

        # 验证 PageManager.write_page 没有被调用
        self.mock_page_manager.write_page.assert_not_called()

    def test_flush_all(self):
        """测试 flush_all 功能"""
        # 加载几个页到缓存 (使用存在于 mock_pages 中的 ID，例如 0, 1, 2)
        page_ids = [0, 1, 2]  # 修正：使用已存在的 ID
        pages = [self.bp_lru.get_page(pid) for pid in page_ids]
        for p in pages:
            self.assertIsNotNone(p)  # 现在应该不会失败了

        # 标记其中两个为脏页 (使用 pages 列表中的实际对象)
        pages[0].is_dirty = True
        pages[2].is_dirty = True
        # 同步更新 mock_pages 字典中的状态（虽然可能不需要，但保持一致）
        self.mock_pages[page_ids[0]].is_dirty = True
        self.mock_pages[page_ids[2]].is_dirty = True

        # 调用 flush_all
        self.bp_lru.flush_all()

        # 验证 PageManager.write_page 被调用了两次，且参数正确
        expected_calls = [call(pages[0]), call(pages[2])]
        # 使用 assert_has_calls 并忽略顺序
        self.mock_page_manager.write_page.assert_has_calls(expected_calls, any_order=True)
        self.assertEqual(self.mock_page_manager.write_page.call_count, 2)

    def test_allocate_page(self):
        """测试 allocate_page 功能"""
        # Mock PageManager.allocate_page 返回一个新页
        new_page = MagicMock()
        new_page.page_id = 100
        new_page.is_dirty = False # allocate 时通常标记为 dirty? 这取决于具体实现
        self.mock_page_manager.allocate_page.return_value = new_page

        # 调用 allocate_page
        allocated_page = self.bp_lru.allocate_page()

        # 验证结果
        self.assertEqual(allocated_page, new_page)
        self.assertIn(new_page.page_id, self.bp_lru.buffer)
        # 验证新页被加入缓存后，如果缓存未满，不会触发驱逐
        # (因为我们初始是空的，池大小是3，加入1个)
        self.assertLessEqual(len(self.bp_lru.buffer), self.bp_lru.pool_size)
        # 验证 PageManager.allocate_page 被调用
        self.mock_page_manager.allocate_page.assert_called_once()

    def test_allocate_page_eviction(self):
        """测试 allocate_page 在缓存满时触发驱逐"""
        # 1. 填满缓存 (使用 LRU)
        loaded_pages = []
        for i in range(self.pool_size):
            page = self.bp_lru.get_page(i)
            self.assertIsNotNone(page)
            loaded_pages.append(page)  # 保存引用

        # 确认缓存已满
        self.assertEqual(len(self.bp_lru.buffer), self.pool_size)

        # 2. 标记其中一个页为脏 (例如，根据 LRU 策略，标记最早会成为 victim 的页)
        # 对于 LRU，如果页是按顺序 0,1,2 加入的，且没有再访问，那么页 0 是 LRU。
        victim_page_id = 0
        victim_page = self.bp_lru.buffer[victim_page_id]
        victim_page.is_dirty = True
        self.mock_pages[victim_page_id].is_dirty = True  # 确保 Mock 对象状态一致

        # 3. Mock PageManager.allocate_page 返回一个新页
        new_page_id = 200
        new_page = MagicMock()
        new_page.page_id = new_page_id
        new_page.is_dirty = True  # 新分配的页通常需要写回
        self.mock_page_manager.allocate_page.return_value = new_page

        # 4. 调用 allocate_page (应触发驱逐页 0)
        allocated_page = self.bp_lru.allocate_page()

        # 5. 验证结果
        self.assertEqual(allocated_page, new_page)
        self.assertIn(new_page_id, self.bp_lru.buffer)
        # 缓存大小应仍为 pool_size
        self.assertEqual(len(self.bp_lru.buffer), self.bp_lru.pool_size)
        # 检查是否驱逐了预期的页 (页 0)
        self.assertNotIn(victim_page_id, self.bp_lru.buffer)
        # 验证被驱逐的脏页被写回
        self.mock_page_manager.write_page.assert_called_once_with(victim_page)  # 修正：检查 victim_page
        # 验证 PageManager.allocate_page 被调用
        self.mock_page_manager.allocate_page.assert_called_once()


    def test_free_page(self):
        """测试 free_page 功能"""
        page_id = 7
        # 先加载页到缓存
        page = self.bp_lru.get_page(page_id)
        self.assertIsNotNone(page)

        # 调用 free_page
        self.bp_lru.free_page(page_id)

        # 验证页已从缓存中移除
        self.assertNotIn(page_id, self.bp_lru.buffer)
        # 验证 PageManager.free_page 被调用
        self.mock_page_manager.free_page.assert_called_once_with(page_id)

    def test_free_page_not_in_buffer(self):
        """测试 free_page 对不在缓存中的页的处理"""
        page_id = 888
        # 调用 free_page
        self.bp_lru.free_page(page_id)

        # 验证页不在缓存中（本来就不存在）
        self.assertNotIn(page_id, self.bp_lru.buffer)
        # 验证 PageManager.free_page 仍被调用（从磁盘释放）
        self.mock_page_manager.free_page.assert_called_once_with(page_id)

    def test_get_stats(self):
        """测试 get_stats 功能"""
        # 初始状态
        stats = self.bp_lru.get_stats()
        self.assertEqual(stats['hit_count'], 0)
        self.assertEqual(stats['miss_count'], 0)
        self.assertEqual(stats['total_requests'], 0)
        self.assertEqual(stats['hit_ratio'], 0)
        self.assertEqual(stats['current_size'], 0)
        self.assertEqual(stats['max_size'], self.pool_size)
        self.assertEqual(stats['policy'], 'LRU')

        # 进行一些访问操作
        self.bp_lru.get_page(1) # Miss
        self.bp_lru.get_page(1) # Hit
        self.bp_lru.get_page(2) # Miss

        # 再次获取统计
        stats = self.bp_lru.get_stats()
        self.assertEqual(stats['hit_count'], 1)
        self.assertEqual(stats['miss_count'], 2)
        self.assertEqual(stats['total_requests'], 3)
        self.assertAlmostEqual(stats['hit_ratio'], 1/3)
        self.assertEqual(stats['current_size'], 2) # 缓存了页 1 和 2
        self.assertEqual(stats['max_size'], self.pool_size)
        self.assertEqual(stats['policy'], 'LRU')

if __name__ == '__main__':
    # 运行测试
    unittest.main()
