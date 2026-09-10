# utils/helpers.py
import unicodedata
from typing import Any, List, Optional, Dict


def display_width(text: Any) -> int:
    """计算字符串在终端中的真实显示宽度（处理全角/东亚宽字符）"""
    s = str(text)
    width = 0
    for ch in s:
        status = unicodedata.east_asian_width(ch)
        if status in ('W', 'F'):
            width += 2
        else:
            width += 1
    return width


def pad_to_width(text: Any, target_width: int, align: str = '<') -> str:
    """根据显示宽度进行空格填充对齐"""
    s = str(text)
    current_width = display_width(s)
    pad_needed = max(0, target_width - current_width)
    if align == '>':
        return ' ' * pad_needed + s
    elif align == '^':
        left = pad_needed // 2
        right = pad_needed - left
        return ' ' * left + s + ' ' * right
    else:  # 默认左对齐
        return s + ' ' * pad_needed


def format_output(rows: List[Dict[str, Any]], columns: Optional[List[str]] = None) -> str:
    """格式化查询结果输出，使用表格边框，支持中英文全半角正确对齐"""
    if not rows:
        return "没有结果"

    if columns is None:
        columns = list(rows[0].keys())

    if not columns:
        return "没有列可显示"

    # 计算每列的最大显示宽度（包括列名和所有数据）
    col_widths = []
    for col in columns:
        max_width = display_width(col)
        for row in rows:
            value = str(row.get(col, 'NULL'))
            max_width = max(max_width, display_width(value))
        col_widths.append(max_width)

    # 构建水平分隔线 (例如: "+-------+----------+--------+")
    separator = "+" + "+".join(["-" * (w + 2) for w in col_widths]) + "+"

    output_lines = []
    # 添加顶部边框
    output_lines.append(separator)

    # 添加表头
    header_line = "| " + " | ".join(pad_to_width(col, w) for col, w in zip(columns, col_widths)) + " |"
    output_lines.append(header_line)

    # 添加表头下方的分隔线
    output_lines.append(separator)

    # 添加数据行
    for row in rows:
        values = [str(row.get(col, 'NULL')) for col in columns]
        row_line = "| " + " | ".join(pad_to_width(v, w) for v, w in zip(values, col_widths)) + " |"
        output_lines.append(row_line)

    # 添加底部边框
    output_lines.append(separator)

    # 返回格式化表格与行数汇总
    result = "\n".join(output_lines)
    result += f"\n\n{len(rows)} row(s) returned"
    return result