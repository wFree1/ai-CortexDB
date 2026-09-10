from collections import OrderedDict
from typing import Optional, Dict
from storage.page import Page, PageManager
from utils.constants import BUFFER_POOL_SIZE
import logging

# 配置一个 logger 用于缓存相关的日志
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class BufferPool:
    def __init__(self, page_manager: PageManager, pool_size: int = BUFFER_POOL_SIZE, policy: str = 'LRU'):
        self.page_manager = page_manager
        self.pool_size = pool_size
        # 验证策略
        if policy not in ['LRU', 'FIFO']:
            raise ValueError(f"Unsupported policy: {policy}. Supported policies are 'LRU', 'FIFO'.")
        self.policy = policy
        # 使用 OrderedDict 实现 LRU/FIFO
        self.buffer: OrderedDict[int, Page] = OrderedDict()
        self.hit_count = 0
        self.miss_count = 0
        # 如果需要 LFU，可能需要额外的数据结构，如 {page_id: frequency}

    def get_page(self, page_id: int) -> Optional[Page]:
        """获取页面。如果页面在缓存中，则根据策略更新其位置（LRU）并增加命中计数；
          如果不在缓存中，则从磁盘加载，增加未命中计数，并管理缓存大小。
        """
        # 检查页面是否在缓存中
        if page_id in self.buffer:
            page = self.buffer[page_id]
            # 对于 LRU，在访问后移动到最近使用的位置
            if self.policy == 'LRU':
                self.buffer.move_to_end(page_id)
            # FIFO: 访问不改变顺序
            self.hit_count += 1
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Cache HIT for page_id: {page_id} (Policy: {self.policy})")
            return page

        # 未命中缓存
        # 从磁盘加载页面
        page = self.page_manager.read_page(page_id)
        if page is None:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Page {page_id} not found on disk.")
            return None

        self.miss_count += 1
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Cache MISS for page_id: {page_id}. Loaded from disk. (Policy: {self.policy})")

        # 添加到缓存
        self.buffer[page_id] = page

        # 如果缓存超过了容量限制，则移除最久未使用的页面
        if self.pool_size > 0 and len(self.buffer) > self.pool_size:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Cache exceeded capacity. Evicting a page...")
            evicted_page_id = self._evict_page() # 调用驱逐
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Evicted page_id: {evicted_page_id} due to capacity overflow. (Policy: {self.policy})")

        return page

    def _evict_page(self) -> Optional[int]:
        """根据指定策略驱逐一页。返回被驱逐的页ID，如果缓存为空则返回None。"""
        if not self.buffer:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Attempted eviction, but buffer is empty.")
            return None

        evicted_page_id = None
        page_to_evict = None

        if self.policy in ['LRU', 'FIFO']:
            # 移除并返回最早插入的项 (FIFO/LRU 驱逐点)
            evicted_page_id, page_to_evict = self.buffer.popitem(last=False)
        else:
            raise ValueError(f"Unsupported policy during eviction: {self.policy}")

        # 如果被驱逐的页是脏页，则刷新到磁盘
        if page_to_evict and page_to_evict.is_dirty:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Flushing dirty page {evicted_page_id} to disk during eviction. (Policy: {self.policy})")
            self.page_manager.write_page(page_to_evict)
            page_to_evict.is_dirty = False # 刷新后标记为干净
        else:
            if logger.isEnabledFor(logging.DEBUG):
               logger.debug(f"Evicting clean page {evicted_page_id}. (Policy: {self.policy})")

        return evicted_page_id


    def flush_page(self, page_id: int):
        """将指定的脏页刷新到磁盘，并标记为干净。"""
        if page_id in self.buffer:
            page = self.buffer[page_id]
            if page.is_dirty:
                self.page_manager.write_page(page)
                page.is_dirty = False
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"Flushed page {page_id} to disk.")

    def flush_all(self):
        """将所有脏页刷新到磁盘。"""
        flushed_count = 0
        for page_id, page in list(self.buffer.items()):
            if page.is_dirty:
                self.page_manager.write_page(page)
                page.is_dirty = False
                flushed_count += 1
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Flushed {flushed_count} dirty pages to disk.")

    def close(self):
        """关闭缓冲池，刷盘所有脏页并清空缓存。"""
        self.flush_all()
        self.buffer.clear()
        if hasattr(self.page_manager, 'close'):
            self.page_manager.close()

    def allocate_page(self) -> Page:
        # 分配新页由 PageManager 完成
        page = self.page_manager.allocate_page()

        # 将新页添加到缓存中
        self.buffer[page.page_id] = page
        page.is_dirty = True   # 新分配的页通常需要写回

        # 如果缓存超过了容量限制，则移除最久未使用的页面
        # 添加 self.pool_size > 0 检查以处理 pool_size 为 0 或负数的边缘情况
        if self.pool_size > 0 and len(self.buffer) > self.pool_size: # 保持 > 逻辑
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Cache exceeded capacity upon allocation. Evicting a page...")
            evicted_page_id = self._evict_page() # 调用驱逐
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Evicted page_id: {evicted_page_id} due to new allocation. (Policy: {self.policy})")

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Allocated and cached new page_id: {page.page_id}")
        return page

    def free_page(self, page_id: int):
        """从缓存和磁盘中释放一个页。"""
        # 如果页在缓存中，先从缓存中移除
        was_in_buffer = page_id in self.buffer
        if was_in_buffer:
            del self.buffer[page_id]
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Freed page {page_id} from cache.")
        # 通知 PageManager 从磁盘释放
        self.page_manager.free_page(page_id)
        if logger.isEnabledFor(logging.DEBUG):
            location_info = " (was in cache)" if was_in_buffer else " (not in cache)"
            logger.debug(f"Freed page {page_id} from disk.{location_info}")

    def get_stats(self) -> Dict[str, int]:
        """获取缓存统计信息。"""
        total_requests = self.hit_count + self.miss_count # 注意：原代码中是 miss_count
        hit_ratio = self.hit_count / total_requests if total_requests > 0 else 0
        return {
            'hit_count': self.hit_count,
            'miss_count': self.miss_count, # 修正键名
            'total_requests': total_requests,
            'hit_ratio': hit_ratio,
            'current_size': len(self.buffer),
            'max_size': self.pool_size,
            'policy': self.policy
        }

    # 重置统计信息
    def reset_stats(self):
        """重置命中和未命中计数器。"""
        self.hit_count = 0
        self.miss_count = 0 # 修正变量名
