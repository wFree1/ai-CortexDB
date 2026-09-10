# agent/runtime/pool.py
import threading
from typing import Optional
from agent.runtime.adapter import CortexDBAdapter
from agent.runtime.session import DatabaseSession
from agent.config import get_config


class DatabasePool:
    """
    CortexDB 线程安全会话连接池.
    管理并发度，保证多 Agent 请求与 Web 接口安全调度底层引擎。
    """
    def __init__(self, data_dir: str = 'data', pool_size: int = 10):
        self.data_dir = data_dir
        self.pool_size = pool_size
        self._lock = threading.RLock()
        self._shared_adapter: Optional[CortexDBAdapter] = None
        self._semaphore = threading.Semaphore(pool_size)

    def _get_shared_adapter(self) -> CortexDBAdapter:
        with self._lock:
            if self._shared_adapter is None:
                self._shared_adapter = CortexDBAdapter(data_dir=self.data_dir)
            return self._shared_adapter

    def acquire(self, timeout: Optional[float] = None) -> DatabaseSession:
        cfg = get_config()
        t = timeout if timeout is not None else cfg.pool_timeout
        acquired = self._semaphore.acquire(timeout=t)
        if not acquired:
            raise TimeoutError(f"DatabasePool acquire timed out after {t}s (pool_size={self.pool_size})")

        adapter = self._get_shared_adapter()
        session = DatabaseSession(adapter)
        return session

    def release(self, session: DatabaseSession):
        session.close()
        self._semaphore.release()

    def close(self):
        with self._lock:
            if self._shared_adapter:
                self._shared_adapter.close()
                self._shared_adapter = None


_global_pool: Optional[DatabasePool] = None
_pool_lock = threading.Lock()


def get_db_pool() -> DatabasePool:
    global _global_pool
    with _pool_lock:
        if _global_pool is None:
            cfg = get_config()
            _global_pool = DatabasePool(data_dir=cfg.data_dir, pool_size=cfg.pool_size)
        return _global_pool
