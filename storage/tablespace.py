# storage/tablespace.py
import os
from typing import Optional
from utils.constants import PAGE_SIZE
from storage.page import Page


class Tablespace:
    """
    表空间单文件存储管理器 (Tablespace Storage Engine)。
    取代散碎的单个 page_*.dat 文件，将所有 4096 字节的数据页连续存储在单一二进制文件中（如 datasphere.db）。
    利用文件偏移量实现 O(1) 定长 Seek 读取与写入：
        磁盘物理偏移量 (Offset) = page_id * 4096
    """

    def __init__(self, db_file_path: str):
        self.file_path = db_file_path
        os.makedirs(os.path.dirname(os.path.abspath(db_file_path)), exist_ok=True)

        # 若文件不存在则以读写模式创建，否则以更新模式打开
        if not os.path.exists(self.file_path):
            self._file = open(self.file_path, "w+b")
        else:
            self._file = open(self.file_path, "r+b")

    @property
    def page_count(self) -> int:
        """获取当前表空间已分配的总页数"""
        self._file.seek(0, os.SEEK_END)
        size = self._file.tell()
        return size // PAGE_SIZE

    def read_page(self, page_id: int) -> Optional[Page]:
        """根据页号直接计算偏移量并读取 4KB 数据页"""
        offset = page_id * PAGE_SIZE
        self._file.seek(0, os.SEEK_END)
        if offset + PAGE_SIZE > self._file.tell():
            return None

        self._file.seek(offset)
        data = self._file.read(PAGE_SIZE)
        if len(data) < PAGE_SIZE:
            return None
        return Page(page_id, data)

    def write_page(self, page: Page):
        """将 4KB 数据页写入指定物理偏移量"""
        offset = page.page_id * PAGE_SIZE
        self._file.seek(offset)
        self._file.write(page.data)
        page.is_dirty = False

    def allocate_page(self) -> Page:
        """在表空间文件末尾追加 4096 字节并返回新页"""
        self._file.seek(0, os.SEEK_END)
        current_size = self._file.tell()
        new_page_id = current_size // PAGE_SIZE

        # 写入 4096 字节空数据扩展文件空间
        empty_page_data = bytearray(PAGE_SIZE)
        self._file.write(empty_page_data)
        self._file.flush()

        page = Page(new_page_id, empty_page_data)
        page.is_dirty = True
        return page

    def flush(self):
        """同步文件缓冲区到磁盘"""
        if self._file and not self._file.closed:
            self._file.flush()
            try:
                os.fsync(self._file.fileno())
            except OSError:
                pass

    def close(self):
        """安全刷盘并关闭表空间文件句柄"""
        if self._file and not self._file.closed:
            self.flush()
            self._file.close()
