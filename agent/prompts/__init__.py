# agent/prompts/__init__.py
import os
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent


def load_prompt(prompt_name: str) -> str:
    """加载指定名称的 prompt 模板文件 (例如: 'system', 'sql_generator')"""
    if not prompt_name.endswith(".md"):
        prompt_name += ".md"
    file_path = _PROMPTS_DIR / prompt_name
    if not file_path.exists():
        raise FileNotFoundError(f"Prompt template {file_path} does not exist.")
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()
