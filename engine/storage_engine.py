# engine/storage_engine.py

from storage.file_manager import FileManager


class StorageEngine:
    def __init__(self, file_manager: FileManager):
        self.file_manager = file_manager

    def create_table(self, table_name: str, columns: list):
        """创建表存储结构"""
        return self.file_manager.create_table_file(table_name, columns)

    def insert_record(self, table_name: str, record: dict):
        """插入记录"""
        return self.file_manager.insert_record(table_name, record)

    def read_records(self, table_name: str, condition: dict = None):
        """读取记录"""
        return self.file_manager.read_records(table_name, condition)

    def delete_records(self, table_name: str, condition: dict = None):
        """删除记录"""
        return self.file_manager.delete_records(table_name, condition)

    def flush(self):
        """刷新所有缓冲数据到磁盘"""
        self.file_manager.flush_all()