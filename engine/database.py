# engine/database.py
import os
import time
import re
import json
import shutil
from io import StringIO
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Generator, Tuple

from sql_compiler.lexer import Lexer
from sql_compiler.parser import Parser
from sql_compiler.semantic import SemanticAnalyzer
from sql_compiler.catalog import Catalog
from sql_compiler.planner import Planner, ExecutionPlan
from storage.file_manager import FileManager
from engine.executor import Executor
from utils.exceptions import (
    DataSphereError,
    SQLSyntaxError,
    SemanticError,
    ConstraintViolationError,
    ExecutionError,
)


def clean_statement_for_lex(statement: str) -> str:
    """清理 SQL 注释（-- 单行注释与 /* */ 多行注释），将注释内容替换为空格以保持严格的行列号对齐"""
    res = list(statement)
    in_string, i = False, 0
    n = len(statement)
    while i < n:
        ch = statement[i]
        if ch == "'" and (i == 0 or statement[i - 1] != '\\'):
            in_string = not in_string
            i += 1
            continue
        if not in_string:
            if ch == '-' and i + 1 < n and statement[i + 1] == '-':
                while i < n and statement[i] != '\n':
                    res[i] = ' '
                    i += 1
                continue
            if ch == '/' and i + 1 < n and statement[i + 1] == '*':
                res[i] = ' '
                res[i + 1] = ' '
                i += 2
                while i < n - 1 and not (statement[i] == '*' and statement[i + 1] == '/'):
                    if statement[i] != '\n':
                        res[i] = ' '
                    i += 1
                if i < n:
                    res[i] = ' '
                if i + 1 < n:
                    res[i + 1] = ' '
                i += 2
                continue
        i += 1
    return "".join(res)


def extract_smart_hints(msg: str) -> List[str]:
    """提取错误信息中的智能纠错提示"""
    hints = []
    for line in (msg or "").splitlines():
        line_s = line.strip()
        if line_s.startswith("智能提示：") or line_s.startswith("智能提示:"):
            hints.append(line_s)
        elif line_s.startswith("提示：") or line_s.startswith("提示:"):
            hints.append(line_s)
        elif "你是否想写" in line_s:
            hints.append(line_s)
    return hints


def iter_sql_statements(text: str) -> Generator[str, None, None]:
    """将包含多条 SQL 的文本切分为单个带分号的完整语句"""
    buf, in_str, escape = [], False, False
    for ch in text:
        buf.append(ch)
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == "'":
                in_str = False
            continue
        else:
            if ch == "'":
                in_str = True
                continue
            if ch == ";":
                stmt = "".join(buf).strip()
                if stmt:
                    yield stmt
                buf.clear()
    tail = "".join(buf).strip()
    if tail.endswith(";"):
        yield tail


@dataclass
class ExecutionResult:
    """SQL 编译与执行结果的结构化封装"""
    sql: str
    success: bool
    data: Optional[List[Dict[str, Any]]] = None
    row_count: int = 0
    message: str = ""
    plan: Optional[Any] = None
    explain_text: Optional[str] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    smart_hints: List[str] = field(default_factory=list)
    compilation_log: List[str] = field(default_factory=list)
    execution_time_ms: float = 0.0
    current_database: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sql": self.sql,
            "success": self.success,
            "data": self.data,
            "row_count": self.row_count,
            "message": self.message,
            "explain_text": self.explain_text,
            "error": self.error,
            "error_type": self.error_type,
            "smart_hints": self.smart_hints,
            "execution_time_ms": self.execution_time_ms,
            "current_database": self.current_database,
        }


class DataSphereDB:
    """
    DataSphere 数据库内核的核心门面类 (Facade)。
    统一封装词法语法分析、语义检查、优化器、执行器和页式存储，
    为外部调用（CLI、测试用例、LangChain Tool、Agent）提供纯净、无状态依赖的 Python API。
    """

    def __init__(self, data_dir: str = 'data', log_dir: Optional[str] = None):
        self.data_dir = data_dir
        self.log_dir = log_dir or os.path.join(data_dir, 'log')
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)

        self.databases_dir = os.path.join(self.data_dir, 'databases')
        os.makedirs(self.databases_dir, exist_ok=True)
        self.current_database = 'datasphere'

        self.file_manager = FileManager(data_dir=self.data_dir)
        self.catalog = Catalog(data_dir=self.data_dir, buffer_pool=self.file_manager.buffer_pool)
        self.executor = Executor(self.file_manager, self.catalog, db=self)
        self.semantic_analyzer = SemanticAnalyzer(self.catalog)
        self.planner = Planner()

    def _get_database_path(self, db_name: str) -> str:
        if db_name == 'datasphere':
            return self.data_dir
        return os.path.join(self.databases_dir, db_name)

    def list_databases(self) -> List[str]:
        """返回所有可用数据库列表"""
        dbs = ['datasphere']
        if os.path.exists(self.databases_dir):
            for entry in sorted(os.listdir(self.databases_dir)):
                full_path = os.path.join(self.databases_dir, entry)
                if os.path.isdir(full_path) and entry not in dbs:
                    dbs.append(entry)
        return dbs

    def create_database(self, db_name: str, if_not_exists: bool = False) -> str:
        """创建全新独立的数据库存储目录与元数据"""
        db_name = db_name.strip()
        if not re.match(r'^[A-Za-z0-9_]+$', db_name):
            raise SemanticError(f"Invalid database name '{db_name}'. Only alphanumeric characters and underscores are allowed.")

        existing = self.list_databases()
        if db_name in existing:
            if if_not_exists:
                return f"Database '{db_name}' already exists (IF NOT EXISTS skipped)."
            raise SemanticError(f"Database '{db_name}' already exists.")

        db_path = self._get_database_path(db_name)
        os.makedirs(db_path, exist_ok=True)
        with open(os.path.join(db_path, 'catalog.json'), 'w', encoding='utf-8') as f:
            json.dump({}, f, indent=2)
        with open(os.path.join(db_path, 'index_roots.json'), 'w', encoding='utf-8') as f:
            json.dump({}, f, indent=2)
        with open(os.path.join(db_path, 'table_files.json'), 'w', encoding='utf-8') as f:
            json.dump({}, f, indent=2)
        return f"Database '{db_name}' created successfully."

    def drop_database(self, db_name: str, if_exists: bool = False) -> str:
        """安全删除指定数据库目录"""
        db_name = db_name.strip()
        if db_name == 'datasphere':
            raise SemanticError("Cannot drop default system database 'datasphere'.")

        existing = self.list_databases()
        if db_name not in existing:
            if if_exists:
                return f"Database '{db_name}' does not exist (IF EXISTS skipped)."
            raise SemanticError(f"Database '{db_name}' does not exist.")

        # 若删除当前库，先平稳切回 datasphere
        if self.current_database == db_name:
            self.use_database('datasphere')

        db_path = self._get_database_path(db_name)
        if os.path.exists(db_path):
            shutil.rmtree(db_path, ignore_errors=True)
        return f"Database '{db_name}' dropped successfully."

    def use_database(self, db_name: str) -> str:
        """运行时动态切换当前激活的工作数据库"""
        db_name = db_name.strip()
        existing = self.list_databases()
        if db_name not in existing:
            raise SemanticError(f"Unknown database '{db_name}'.")

        if self.current_database == db_name:
            return f"Database changed to '{db_name}'."

        # 1. 刷盘并关闭旧库表空间
        if hasattr(self.file_manager, "close"):
            self.file_manager.close()

        # 2. 挂载新库
        new_path = self._get_database_path(db_name)
        os.makedirs(new_path, exist_ok=True)
        self.file_manager = FileManager(data_dir=new_path)
        self.catalog = Catalog(data_dir=new_path, buffer_pool=self.file_manager.buffer_pool)
        self.executor = Executor(self.file_manager, self.catalog, db=self)
        self.semantic_analyzer = SemanticAnalyzer(self.catalog)
        self.current_database = db_name
        return f"Database changed to '{db_name}'."

    def execute(self, sql: str, actually_execute: bool = True) -> ExecutionResult:
        """
        编译并执行一条 SQL 语句。

        :param sql: 单条 SQL 语句字符串（可含分号）
        :param actually_execute: 若为 False，仅完成词法/语法/语义/逻辑计划生成，不触碰磁盘和真实数据
        :return: ExecutionResult 结构化结果对象
        """
        stmt = sql.strip()
        if not stmt:
            return ExecutionResult(sql=sql, success=True, message="Empty statement.", current_database=self.current_database)

        start_time = time.perf_counter()
        log_lines = [f"SQL 语句: {stmt}"]
        sink = StringIO()

        try:
            # 1. 词法分析 (Lexer)
            clean = clean_statement_for_lex(stmt)
            tokens = Lexer(clean).get_tokens()
            if not tokens:
                return ExecutionResult(
                    sql=stmt,
                    success=False,
                    error="[词法错误] 空语句或无效输入",
                    error_type="SQLSyntaxError",
                )

            # 2. 语法分析 (Parser)
            with redirect_stdout(sink):
                parser = Parser(tokens, source_text=stmt)
                ast = parser.parse()
            parse_out = sink.getvalue()
            sink.seek(0); sink.truncate(0)
            if parse_out.strip():
                log_lines.append(parse_out.strip())

            # 3. 语义分析 (SemanticAnalyzer)
            with redirect_stdout(sink):
                sem_res = self.semantic_analyzer.analyze(ast)
            sem_out = sink.getvalue()
            sink.seek(0); sink.truncate(0)
            if sem_out.strip():
                log_lines.append(sem_out.strip())
            if isinstance(sem_res, str) and sem_res.strip():
                log_lines.append(sem_res.strip())

            # 4. 执行计划与谓词下推优化 (Planner & Optimizer)
            with redirect_stdout(sink):
                plan = self.planner.generate_plan(ast)
            plan_out = sink.getvalue()
            sink.seek(0); sink.truncate(0)
            if plan_out.strip():
                log_lines.append(plan_out.strip())

            explain_text = getattr(plan, "explain", None) if hasattr(plan, "explain") else None
            if isinstance(explain_text, str) and explain_text.strip():
                log_lines.append("—— 优化讲解（谓词下推） ——\n" + explain_text)

            # 5. 实际物理执行 (Executor)
            data = None
            row_count = 0
            message = ""

            if actually_execute:
                with redirect_stdout(StringIO()):
                    exec_result = self.executor.execute(plan)

                if isinstance(exec_result, list):
                    data = exec_result
                    row_count = len(exec_result)
                    message = f"{row_count} row(s) returned"
                elif isinstance(exec_result, str):
                    message = exec_result
                    # 解析受影响行数
                    match = re.search(r'(\d+)\s+row\(s\)', exec_result)
                    if match:
                        row_count = int(match.group(1))
                    elif "Updated" in exec_result:
                        m_up = re.search(r'Updated\s+(\d+)', exec_result)
                        if m_up:
                            row_count = int(m_up.group(1))
            else:
                message = "Validation successful (plan generated, execution skipped)."

            elapsed_ms = (time.perf_counter() - start_time) * 1000.0

            return ExecutionResult(
                sql=stmt,
                success=True,
                data=data,
                row_count=row_count,
                message=message,
                plan=plan,
                explain_text=explain_text,
                compilation_log=log_lines,
                execution_time_ms=elapsed_ms,
                current_database=self.current_database,
            )

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            error_str = str(e)
            leftover_prints = sink.getvalue()
            if leftover_prints.strip():
                log_lines.append(leftover_prints.strip())
            log_lines.append(error_str)

            hints = extract_smart_hints(error_str)
            err_type = type(e).__name__
            if "外键约束" in error_str or "Primary key" in error_str:
                err_type = "ConstraintViolationError"
            elif "语义错误" in error_str:
                err_type = "SemanticError"
            elif "语法错误" in error_str or "词法错误" in error_str or "Syntax" in error_str:
                err_type = "SQLSyntaxError"

            return ExecutionResult(
                sql=stmt,
                success=False,
                error=error_str,
                error_type=err_type,
                smart_hints=hints,
                compilation_log=log_lines,
                execution_time_ms=elapsed_ms,
                current_database=self.current_database,
            )

    def validate(self, sql: str) -> ExecutionResult:
        """纯内存语法与语义校验（不落盘、不执行）"""
        return self.execute(sql, actually_execute=False)

    def execute_batch(self, sql_script: str) -> List[ExecutionResult]:
        """批量执行 SQL 脚本"""
        results = []
        for stmt in iter_sql_statements(sql_script):
            results.append(self.execute(stmt, actually_execute=True))
        return results

    def get_schema_summary(self) -> str:
        """获取结构化格式的数据库所有表 Schema 概览"""
        return self.catalog.get_schema_summary()

    def get_catalog_dict(self) -> Dict[str, Any]:
        """获取元数据字典"""
        return self.catalog.to_dict()

    def close(self):
        """显式刷新所有脏缓冲页并释放资源"""
        if hasattr(self.file_manager, "close"):
            self.file_manager.close()
