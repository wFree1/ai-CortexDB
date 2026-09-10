# agent/tools/diagnostics.py
import re
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class CompilerDiagnostic(BaseModel):
    is_valid: bool
    stage: str = "ok"                     # lexical, syntax, semantic, planning, ok
    error_code: str = "NONE"             # UNKNOWN_COLUMN, UNKNOWN_TABLE, SYNTAX_ERROR, etc.
    line: Optional[int] = None
    column: Optional[int] = None
    caret_line: Optional[str] = None
    message: str = ""
    hints: List[str] = Field(default_factory=list)

    def to_correction_prompt(self) -> str:
        """格式化为反哺给 LLM 纠错的结构化指导文本"""
        if self.is_valid:
            return "Compiler Pre-check: PASS (Valid SQL)"
        res = [
            f"❌ [Compiler Diagnostic Error]",
            f"Stage: {self.stage.upper()}",
            f"ErrorCode: {self.error_code}",
            f"Message: {self.message}"
        ]
        if self.line is not None and self.column is not None:
            res.append(f"Position: line={self.line}, col={self.column}")
        if self.caret_line:
            res.append(f"Error Context:\n{self.caret_line}")
        if self.hints:
            res.append("Compiler Hints:")
            for h in self.hints:
                res.append(f"  - {h}")
        return "\n".join(res)


class DiagnosticAdapter:
    """
    将 DataSphere 错误信息转换为统一 CompilerDiagnostic 对象
    """
    @staticmethod
    def parse_error(error_msg: str, error_type: Optional[str] = None, hints: Optional[List[str]] = None) -> CompilerDiagnostic:
        if not error_msg:
            return CompilerDiagnostic(is_valid=True)

        # 匹配行号与列号 (line=X, col=Y)
        line, col = None, None
        m_pos = re.search(r"\(line=(\d+),\s*col=(\d+)\)", error_msg)
        if m_pos:
            line = int(m_pos.group(1))
            col = int(m_pos.group(2))

        # 匹配可能的光标行
        lines = error_msg.splitlines()
        caret_context = []
        for i, l in enumerate(lines):
            if "^" in l:
                if i > 0:
                    caret_context.append(lines[i - 1])
                caret_context.append(l)
                break
        caret_str = "\n".join(caret_context) if caret_context else None

        # 分类
        stage = "unknown"
        code = "GENERIC_ERROR"
        low = error_msg.lower()

        if "词法" in error_msg or "lex" in low:
            stage = "lexical"
            code = "LEXICAL_ERROR"
        elif "语法" in error_msg or "syntax" in low or "期望" in error_msg:
            stage = "syntax"
            code = "SYNTAX_ERROR"
        elif "语义" in error_msg or "不存在" in error_msg or "类型不匹配" in error_msg:
            stage = "semantic"
            if "表" in error_msg and "不存在" in error_msg:
                code = "UNKNOWN_TABLE"
            elif "列" in error_msg and "不存在" in error_msg:
                code = "UNKNOWN_COLUMN"
            elif "类型" in error_msg:
                code = "TYPE_ERROR"
            elif "外键" in error_msg or "主键" in error_msg:
                code = "CONSTRAINT_ERROR"
            else:
                code = "SEMANTIC_ERROR"

        return CompilerDiagnostic(
            is_valid=False,
            stage=stage,
            error_code=code,
            line=line,
            column=col,
            caret_line=caret_str,
            message=error_msg.strip(),
            hints=hints or []
        )


import json
from langchain_core.tools import tool
from agent.tools.base import ToolSpec, RiskLevel

DIAGNOSTICS_TOOL_SPEC = ToolSpec(
    name="cortex_diagnostics",
    description="获取 DataSphere 数据库健康诊断全景报告，包括表健康度、行数统计、BufferPool 状态与潜在缺失索引预警。",
    risk_level=RiskLevel.READ,
    permissions=["dba.diagnostics"],
    timeout=10.0,
    retryable=True
)


def get_diagnostics_tool(adapter):
    @tool(DIAGNOSTICS_TOOL_SPEC.name, description=DIAGNOSTICS_TOOL_SPEC.description)
    def cortex_diagnostics() -> str:
        """
        全面诊断数据库当前的存储状态、系统表完备性、缓存性能并输出健康建议。
        """
        diag = adapter.get_diagnostics()
        return json.dumps(diag, ensure_ascii=False, indent=2)

    return cortex_diagnostics

