# agent/api/dependencies.py
from typing import Optional
from pathlib import Path
from agent.runtime.adapter import CortexDBAdapter
from agent.config import get_config
from agent.models.router import ModelRouter
from agent.memory.manager import MemoryManager
from agent.runtime.events import EventBus, get_event_bus
from agent.security.firewall import SQLFirewall
from agent.services.execution import ExecutionService
from agent.services.streaming import StreamingService
from agent.services.task import TaskService

_execution_service: Optional[ExecutionService] = None
_streaming_service: Optional[StreamingService] = None
_task_service: Optional[TaskService] = None


def get_services():
    global _execution_service, _streaming_service, _task_service
    if _execution_service is None:
        data_dir = Path(get_config().data_dir)
        if not data_dir.is_absolute():
            data_dir = Path(__file__).resolve().parents[2] / data_dir
        adapter = CortexDBAdapter(data_dir=str(data_dir))
        model_client = ModelRouter()
        memory_mgr = MemoryManager()
        event_bus = get_event_bus()
        firewall = SQLFirewall()
        _execution_service = ExecutionService(adapter, model_client, memory_mgr, event_bus, firewall)
        _streaming_service = StreamingService(_execution_service, event_bus)
        _task_service = TaskService()
    return _execution_service, _streaming_service, _task_service


def close_services():
    global _execution_service, _streaming_service, _task_service
    if _execution_service is not None:
        _execution_service.close()
    _execution_service = None
    _streaming_service = None
    _task_service = None
