import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.api import api_router
from app.db.database import engine, AsyncSessionLocal
from app.db.base import Base
from app.crud import container as crud_container

logger = logging.getLogger(__name__)

# ─── 定时任务参数 ────────────────────────────────────────
STALE_CHECK_INTERVAL = 60    # 每 60 秒扫描一次
HEARTBEAT_TIMEOUT = 120      # 心跳超时阈值：2 分钟


async def _stale_container_cleanup_loop():
    """后台循环：定期扫描并停止心跳超时的容器"""
    logger.info("[定时任务] 心跳超时容器清理任务已启动")
    while True:
        await asyncio.sleep(STALE_CHECK_INTERVAL)
        try:
            async with AsyncSessionLocal() as db:
                stale = await crud_container.find_stale_containers(
                    db, timeout_seconds=HEARTBEAT_TIMEOUT
                )
                for container in stale:
                    logger.info(
                        f"[定时任务] 容器 {container.id} (学生 {container.student_id}) "
                        f"心跳超时，自动停止"
                    )
                    await crud_container.stop_container(db, container)
        except Exception as e:
            logger.error(f"[定时任务] Stale container cleanup error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan：启动 → yield → 关闭"""
    # 启动后台清理任务
    task = asyncio.create_task(_stale_container_cleanup_loop())
    logger.info("🚀 Edubot Twin API 启动中...")
    logger.info("📚 API 文档: http://localhost:8000/docs")

    yield  # 应用运行中

    # 关闭时取消后台任务
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await engine.dispose()
    logger.info("👋 Edubot Twin API 已关闭")


# 创建 FastAPI 实例
app = FastAPI(
    title="Edubot Twin API",
    description="数字孪生机器人实训平台后端 API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite 开发服务器
        "http://localhost:3000",  # 备用端口
        "http://localhost:4000",  # 新增前端端口
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载 API 路由
app.include_router(api_router, prefix="/api/v1")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
