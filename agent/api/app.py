# agent/api/app.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from agent.api.routes_agent import router as agent_router
from agent.api.routes_sql import router as sql_router
from agent.api.routes_dba import router as dba_router
from agent.api.routes_tasks import router as tasks_router
from agent.api.routes_memory import router as memory_router
from agent.api.dependencies import get_services


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 初始化单例服务
    exec_svc, _, _ = get_services()
    yield
    # 关闭数据库适配器连接
    exec_svc.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="CortexDB Database-Native Agent Runtime API",
        version="2.0.0",
        description="DataSphere 自研关系型数据库内核驱动的 Native Agent 运行时服务",
        lifespan=lifespan
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册各模块路由
    app.include_router(agent_router)
    app.include_router(sql_router)
    app.include_router(dba_router)
    app.include_router(tasks_router)
    app.include_router(memory_router)

    @app.get("/health")
    def health_check():
        return {
            "status": "HEALTHY",
            "service": "CortexDB Native Agent Runtime",
            "version": "2.0.0"
        }

    return app


app = create_app()
