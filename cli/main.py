# cli/main.py
import sys
import os
from io import StringIO
from datetime import datetime

# 屏蔽底层 DEBUG 日志，保持控制台整洁
import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logging.getLogger("storage.buffer").setLevel(logging.WARNING)
logging.getLogger("storage").setLevel(logging.WARNING)
logging.getLogger("catalog").setLevel(logging.WARNING)

# 确保在 Windows 终端中输出 UTF-8，避免中文乱码
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# 让 cli/.. 成为 import 根
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.helpers import format_output
from engine.database import (
    DataSphereDB,
    ExecutionResult,
    clean_statement_for_lex as _clean_statement_for_lex,
    extract_smart_hints as _extract_smart_hints,
    iter_sql_statements as _iter_sql_statements,
)

# === 日志目录 ===
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "log")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, f"compile_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")


class DatabaseCLI:
    def __init__(self, data_dir: str = 'data', log_dir: str = None):
        self.data_dir = data_dir
        self.log_dir = log_dir or LOG_DIR
        self.db = DataSphereDB(data_dir=self.data_dir, log_dir=self.log_dir)

        # 兼容原有属性访问
        self.catalog = self.db.catalog
        self.file_manager = self.db.file_manager
        self.executor = self.db.executor
        self.semantic_analyzer = self.db.semantic_analyzer
        self.planner = self.db.planner

        # 日志与统计（仅本次会话）
        self._log_lines = []
        self._success_cnt = 0
        self._total_cnt = 0
        self._show_optimize_to_console = False

    def process_and_log(self, sql_with_semicolon: str, actually_execute: bool = True):
        """
        完整处理一条 SQL，并把详细过程写入内存日志。
        成功/失败统计在此维护；仅把执行结果及智能提示即时输出到控制台。
        """
        stmt = sql_with_semicolon.strip()
        if not stmt:
            return None

        self._total_cnt += 1
        idx = self._total_cnt

        res: ExecutionResult = self.db.execute(stmt, actually_execute=actually_execute)

        # 记录头部
        self._log_lines.append(f"\n>>> 处理第 {idx} 条 SQL 语句 <<<")
        for line in res.compilation_log:
            self._log_lines.append(line)

        if res.success:
            self._success_cnt += 1
            if actually_execute:
                if res.data is not None:
                    print(format_output(res.data) if res.data else "No results returned.")
                elif res.message:
                    print(res.message)
            return True
        else:
            if res.error:
                self._log_lines.append(res.error)
                print(f"[错误] {res.error}")
            for h in res.smart_hints:
                print(h)
            return None

    def process_file(self, path: str):
        """批处理一个 .sql 文件（逐条语句执行 + 写入详细日志）"""
        if not os.path.exists(path):
            print(f"[错误] 文件不存在: {path}")
            return
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        for stmt in _iter_sql_statements(text):
            self.process_and_log(stmt, actually_execute=True)

    def _read_stmt(self, prompt="SQL> "):
        """
        交互输入：支持多行；读到“分号（字符串外）”结束，返回包含分号的完整语句。
        """
        buf, in_str = [], False
        while True:
            try:
                line = input(prompt if not buf else "... ")
            except EOFError:
                return "__EXIT__"

            raw = line.strip()
            low = raw.lower()

            if not buf and (low.startswith(":read ") or low.startswith(":r ")):
                _, _, path = raw.partition(" ")
                path = path.strip()
                if path:
                    self.process_file(path)
                return ""

            if not buf and low in ("quit", "quit;", "exit", "exit;"):
                return "__EXIT__"

            buf.append(line)
            text = "\n".join(buf)
            i = 0
            while i < len(text):
                ch = text[i]
                if ch == ";" and not in_str:
                    return text[: i + 1].strip()
                if ch == "'" and (i == 0 or text[i - 1] != "\\"):
                    in_str = not in_str
                i += 1

    def run(self):
        # 若通过命令行参数传入 .sql 文件，先运行该文件后退出
        if len(sys.argv) >= 2 and sys.argv[1].lower().endswith(".sql"):
            self.process_file(sys.argv[1])
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                f.write("=== 详细编译日志（本次会话） ===\n")
                f.write("\n".join(self._log_lines))
            print(f"成功处理 {self._success_cnt} / {self._total_cnt} 条 SQL 语句！")
            print("SQL 编译器执行完成！详细编译日志已保存到：")
            print(LOG_FILE)
            self.db.close()
            return

        print("Welcome to DataSphere CLI")
        print("多行输入；以 ';' 结束一条语句。输入 quit/exit 退出。")
        print("额外命令：:read <path>  或  :r <path>  —— 从文件读取并执行 SQL 脚本。")

        while True:
            stmt = self._read_stmt()
            if stmt in ("__EXIT__", None):
                break
            if not stmt.strip():
                continue
            self.process_and_log(stmt, actually_execute=True)

        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("=== 详细编译日志（本次会话） ===\n")
            f.write("\n".join(self._log_lines))

        print(f"成功处理 {self._success_cnt} / {self._total_cnt} 条 SQL 语句！")
        print("SQL 编译器执行完成！详细编译日志已保存到：")
        print(LOG_FILE)
        self.db.close()


def main():
    cli = DatabaseCLI()
    cli.run()


if __name__ == "__main__":
    main()
