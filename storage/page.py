import struct
import os
from typing import Optional
from utils.constants import PAGE_SIZE


class Page:
    def __init__(self, page_id: int, data: bytes = None):
        self.page_id = page_id
        # 关键修改：确保 self.data 是一个可变的 bytearray
        if data is None:
            self.data = bytearray(PAGE_SIZE)
        else:
            # 如果传入的是 bytes，将其转换为 bytearray
            if isinstance(data, bytes):
                self.data = bytearray(data)
            elif isinstance(data, bytearray):
                self.data = data
            else:
                raise TypeError("data must be bytes or bytearray")

        self.is_dirty = False
        self.pin_count = 0

    def read_data(self, offset: int, size: int) -> bytes:
        return self.data[offset:offset + size]

    def write_data(self, offset: int, data: bytes):
        self.data[offset:offset + len(data)] = data
        self.is_dirty = True

    def get_int(self, offset: int, size: int = 4) -> int:
        """从指定偏移量读取一个整数，支持不同大小 (1, 2, 4, 8 字节)"""
        if size not in [1, 2, 4, 8]:
            raise ValueError(f"Unsupported integer size: {size}. Supported sizes are 1, 2, 4, 8.")

        # 根据大小选择格式字符
        fmt = {1: 'b', 2: 'h', 4: 'i', 8: 'q'}[size]  # 'b'=int8, 'h'=int16, 'i'=int32, 'q'=int64

        return struct.unpack(fmt, self.data[offset:offset + size])[0]

    def set_int(self, offset: int, value: int, size: int = 4):
        """在指定偏移量写入一个整数，支持不同大小 (1, 2, 4, 8 字节)"""
        if size not in [1, 2, 4, 8]:
            raise ValueError(f"Unsupported integer size: {size}. Supported sizes are 1, 2, 4, 8.")

        # 根据大小选择格式字符
        fmt = {1: 'b', 2: 'h', 4: 'i', 8: 'q'}[size]

        self.data[offset:offset + size] = struct.pack(fmt, value)
        self.is_dirty = True

    def get_string(self, offset: int, length: int) -> str:
        return self.data[offset:offset + length].decode('utf-8').rstrip('\x00')

    def set_string(self, offset: int, value: str, length: int):
        encoded = value.encode('utf-8')
        padded = encoded.ljust(length, b'\x00')
        self.data[offset:offset + length] = padded
        self.is_dirty = True


class PageManager:
    def __init__(self, data_dir: str = 'data'):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        # 单文件表空间：将所有 4KB 数据页保存在统一的 datasphere.db 中
        from storage.tablespace import Tablespace
        db_path = os.path.join(data_dir, 'datasphere.db') if not data_dir.endswith('.db') else data_dir
        self.tablespace = Tablespace(db_path)

    def read_page(self, page_id: int) -> Optional[Page]:
        return self.tablespace.read_page(page_id)

    def write_page(self, page: Page):
        self.tablespace.write_page(page)

    def allocate_page(self) -> Page:
        return self.tablespace.allocate_page()

    def free_page(self, page_id: int):
        pass

    def flush(self):
        self.tablespace.flush()

    def close(self):
        self.tablespace.close()