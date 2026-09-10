# agent/security/policy.py
from pydantic import BaseModel
from agent.config import get_config


class SecurityPolicy(BaseModel):
    """
    CortexDB 安全执行策略规范
    """
    allow_write: bool = False
    allow_ddl: bool = False
    require_approval_for_admin: bool = True
    require_approval_for_write: bool = False
    max_query_timeout_seconds: float = 30.0
    deny_dangerous_always: bool = True

    @classmethod
    def from_config(cls):
        cfg = get_config()
        return cls(
            allow_write=cfg.allow_write,
            allow_ddl=cfg.allow_ddl,
            require_approval_for_admin=cfg.require_approval,
            require_approval_for_write=False,
            max_query_timeout_seconds=cfg.agent_timeout,
            deny_dangerous_always=True
        )
