# agent/memory/preference.py
from typing import Dict, Any, Optional
from agent.memory.base import BaseMemory


class PreferenceMemory(BaseMemory):
    """
    偏好记忆 (Preference Memory)
    记录全局或用户维度的格式偏好、返回行数偏好与风格设置。
    """

    def __init__(self):
        self._prefs: Dict[str, Any] = {
            "format": "markdown",
            "show_explain": True,
            "show_metrics": True,
            "dialect": "datasphere"
        }

    def get(self, key: str) -> Optional[Any]:
        return self._prefs.get(key)

    def set(self, key: str, value: Any, metadata: Optional[Dict[str, Any]] = None) -> None:
        self._prefs[key] = value

    def get_all(self) -> Dict[str, Any]:
        return dict(self._prefs)

    def clear(self) -> None:
        self._prefs.clear()
