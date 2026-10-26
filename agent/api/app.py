# agent/api/app.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from agent.api.routes_agent import router as agent_router
from agent.api.routes_sql import router as sql_router
from agent.api.routes_dba import router as dba_router
from agent.api.routes_tasks import router as tasks_router
from agent.api.routes_memory import router as memory_router
from agent.api.dependencies import close_services, get_services
from web.studio_routes import STATIC_DIR, router as studio_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 初始化单例服务
    get_services()
    try:
        yield
    finally:
        close_services()


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
    app.include_router(studio_router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/health")
    def health_check():
        return {
            "status": "HEALTHY",
            "service": "CortexDB Native Agent Runtime",
            "version": "2.0.0"
        }

    return app


app = create_app()
