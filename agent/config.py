# agent/config.py
import os
from typing import Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()


class AgentConfig(BaseModel):
    # Model configuration
    model_provider: str = Field(default_factory=lambda: os.getenv("MODEL_PROVIDER", "openai"))
    model_name: str = Field(default_factory=lambda: os.getenv("MODEL_NAME", "qwen3.7-plus"))
    openai_api_base: str = Field(default_factory=lambda: os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"))
    openai_api_key: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    temperature: float = Field(default_factory=lambda: float(os.getenv("TEMPERATURE", "0.0")))

    # Agent limits & retry
    max_retries: int = Field(default_factory=lambda: int(os.getenv("AGENT_MAX_RETRIES", "3")))
    max_result_rows: int = Field(default_factory=lambda: int(os.getenv("AGENT_MAX_RESULT_ROWS", "1000")))
    max_context_rows: int = Field(default_factory=lambda: int(os.getenv("AGENT_MAX_CONTEXT_ROWS", "100")))
    timeout_seconds: int = Field(default_factory=lambda: int(os.getenv("AGENT_TIMEOUT", "300")))
    router_model: Optional[str] = Field(default_factory=lambda: os.getenv("ROUTER_MODEL", None))
    dba_model: Optional[str] = Field(default_factory=lambda: os.getenv("DBA_MODEL", None))

    @property
    def agent_timeout(self) -> int:
        return self.timeout_seconds

    # Security & Policy
    allow_write: bool = Field(default_factory=lambda: os.getenv("AGENT_ALLOW_WRITE", "true").lower() in ("true", "1"))
    allow_ddl: bool = Field(default_factory=lambda: os.getenv("AGENT_ALLOW_DDL", "true").lower() in ("true", "1"))
    require_approval: bool = Field(default_factory=lambda: os.getenv("AGENT_REQUIRE_APPROVAL", "true").lower() in ("true", "1"))

    # Database & Pool
    data_dir: str = Field(default_factory=lambda: os.getenv("CORTEX_DATA_DIR", "data"))
    pool_size: int = Field(default_factory=lambda: int(os.getenv("CORTEX_DB_POOL_SIZE", "10")))
    pool_max_size: int = Field(default_factory=lambda: int(os.getenv("CORTEX_DB_POOL_MAX_SIZE", "50")))
    pool_timeout: float = Field(default_factory=lambda: float(os.getenv("CORTEX_DB_POOL_TIMEOUT", "5.0")))

    # Service & API
    api_host: str = Field(default_factory=lambda: os.getenv("CORTEX_API_HOST", "127.0.0.1"))
    api_port: int = Field(default_factory=lambda: int(os.getenv("CORTEX_API_PORT", "8000")))

    @property
    def has_api_key(self) -> bool:
        return bool(self.openai_api_key and self.openai_api_key.strip() and self.openai_api_key != "your_api_key_here")


# 单例全局配置
_global_config: Optional[AgentConfig] = None


def get_config() -> AgentConfig:
    global _global_config
    if _global_config is None:
        _global_config = AgentConfig()
    return _global_config


def set_config(cfg: AgentConfig):
    global _global_config
    _global_config = cfg
