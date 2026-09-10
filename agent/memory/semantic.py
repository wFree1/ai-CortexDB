# agent/memory/semantic.py
from typing import Dict, Any, List, Optional
from agent.memory.base import BaseMemory


class SemanticMemory(BaseMemory):
    """
    语义知识记忆 (Semantic Memory)
    存储表间逻辑关联路径（如 employees.dept_id <-> departments.dept_id）与业务实体同义词字典。
    """

    def __init__(self):
        # 预设 DataSphere 业务语义字典
        self._synonyms: Dict[str, str] = {
            "员工": "employees",
            "雇员": "employees",
            "部门": "departments",
            "薪资": "salary",
            "工资": "salary",
            "在职": "is_active",
            "入职时间": "hire_date"
        }
        self._join_paths: List[Dict[str, str]] = [
            {
                "from_table": "employees",
                "from_col": "dept_id",
                "to_table": "departments",
                "to_col": "dept_id",
                "relation": "MANY_TO_ONE"
            }
        ]

    def add_synonym(self, term: str, physical_name: str):
        self._synonyms[term] = physical_name

    def get_synonyms(self) -> Dict[str, str]:
        return dict(self._synonyms)

    def get_join_paths(self) -> List[Dict[str, str]]:
        return list(self._join_paths)

    def get(self, key: str) -> Optional[Any]:
        if key == "synonyms":
            return self._synonyms
        if key == "join_paths":
            return self._join_paths
        return self._synonyms.get(key)

    def set(self, key: str, value: Any, metadata: Optional[Dict[str, Any]] = None) -> None:
        self._synonyms[key] = str(value)

    def clear(self) -> None:
        self._synonyms.clear()
        self._join_paths.clear()
