# observability/logging.py
import logging
import sys
import json
import time
from typing import Dict, Any, Optional


class StructuredFormatter(logging.Formatter):
    """
    JSON 结构化日志格式化器
    """
    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage()
        }
        if hasattr(record, "trace_id"):
            log_entry["trace_id"] = record.trace_id
        if hasattr(record, "task_id"):
            log_entry["task_id"] = record.task_id
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


def setup_observability_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("cortex")
    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"))
        logger.addHandler(handler)
    return logger
