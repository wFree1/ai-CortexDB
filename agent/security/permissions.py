# agent/security/permissions.py
from typing import Set, Dict, List


class PermissionManager:
    """
    权限与角色鉴权中枢 (RBAC)
    """

    ROLE_PERMISSIONS: Dict[str, Set[str]] = {
        "admin": {
            "sql.read", "sql.write", "sql.admin", "sql.execute",
            "dba.metrics", "dba.advisor", "dba.diagnostics"
        },
        "developer": {
            "sql.read", "sql.write", "sql.execute",
            "dba.metrics", "dba.advisor"
        },
        "analyst": {
            "sql.read", "sql.execute"
        },
        "guest": {
            "sql.read"
        }
    }

    @classmethod
    def check_permissions(cls, role: str, required_permissions: List[str]) -> bool:
        allowed = cls.ROLE_PERMISSIONS.get(role.lower(), set())
        for req in required_permissions:
            if req not in allowed:
                return False
        return True
