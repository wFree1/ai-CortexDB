# 输入处理：支持 SQL 文件或标准输入

import sys
import re


class InputHandler:
    """输入处理器：支持文件和标准输入"""

    @staticmethod
    def load_from_file(filename):
        """从文件加载 SQL 内容"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            raise Exception(f"[系统错误，位置: N/A，原因说明: 无法找到文件 '{filename}']")
        except Exception as e:
            raise Exception(f"[系统错误，位置: N/A，原因说明: 读取文件时发生错误: {str(e)}]")

    @staticmethod
    def load_from_stdin():
        """从标准输入读取 SQL 内容"""
        print("请输入 SQL 语句（输入 'quit' 或按 Ctrl+D 退出）：")
        lines = []
        try:
            while True:
                line = input("MiniDB> ")
                if line.strip().lower() == 'quit':
                    break
                lines.append(line)
        except EOFError:
            pass  # Ctrl+D 退出
        return "\n".join(lines)

    @staticmethod
    def split_statements(sql_content):
        """按分号分割 SQL 语句，保留分号"""
        statements = []
        current_stmt = ""
        in_string = False
        escape_next = False

        for i, char in enumerate(sql_content):
            if char == "'" and not escape_next:
                in_string = not in_string
            elif char == '\\' and in_string:
                escape_next = True
                continue
            else:
                escape_next = False

            current_stmt += char

            if char == ';' and not in_string:
                statements.append(current_stmt.strip())
                current_stmt = ""

        # 添加最后一个不完整的语句（用于错误处理）
        if current_stmt.strip():
            statements.append(current_stmt.strip())

        return statements