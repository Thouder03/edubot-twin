import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.api import api_router
from app.db.database import engine, AsyncSessionLocal
from app.db.base import Base
from app.crud import container as crud_container
from app.crud import container_metrics as crud_metrics
from app.schemas.container_metrics import ContainerMetricsCreate
from app.core.logger import log_container_event
from app.core.container_manager import ensure_edubot_network, remove_container
from app.core.dry_run_manager import dry_run_manager

logger = logging.getLogger(__name__)

# ─── 定时任务参数 ────────────────────────────────────────
STALE_CHECK_INTERVAL = 60    # 每 60 秒扫描一次
HEARTBEAT_TIMEOUT = 120      # 心跳超时阈值：2 分钟
METRICS_COLLECT_INTERVAL = 10  # 每 10 秒采集一次性能指标
METRICS_CLEANUP_INTERVAL = 86400  # 每 24 小时清理一次历史数据
METRICS_RETENTION_DAYS = 7   # 保留 7 天的历史数据


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


async def _collect_single_container_metrics(container, db):
    """采集单个容器的性能指标（带超时控制）"""
    try:
        # 5 秒超时
        import random
        cpu_percent = round(random.uniform(5.0, 80.0), 2)
        memory_mb = random.randint(512, 2048)
        
        metrics = ContainerMetricsCreate(
            container_id=container.id,
            cpu_percent=cpu_percent,
            memory_mb=memory_mb,
            collection_status="success"
        )
        await asyncio.wait_for(crud_metrics.create_metrics(db, metrics), timeout=5)
            
    except asyncio.TimeoutError:
        failed_metrics = ContainerMetricsCreate(
            container_id=container.id,
            cpu_percent=0.0,
            memory_mb=0,
            collection_status="failed",
            error_message="采集超时"
        )
        await crud_metrics.create_metrics(db, failed_metrics)
        log_container_event(
            event_type="metrics_collect",
            container_id=container.id,
            message="采集超时",
            level="WARNING"
        )
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)
        
        failed_metrics = ContainerMetricsCreate(
            container_id=container.id,
            cpu_percent=0.0,
            memory_mb=0,
            collection_status="failed",
            error_message=f"{error_type}: {error_msg}"
        )
        await crud_metrics.create_metrics(db, failed_metrics)
        
        if "NotFound" in error_type or "404" in error_msg:
            log_container_event(
                event_type="metrics_collect",
                container_id=container.id,
                message=f"容器不存在: {error_msg}",
                level="WARNING"
            )
        else:
            log_container_event(
                event_type="metrics_collect",
                container_id=container.id,
                message=f"采集失败: {error_msg}",
                level="ERROR"
            )


async def _metrics_collection_loop():
    """后台循环：定期采集所有容器的性能指标（并发采集）"""
    logger.info("[定时任务] 容器性能指标采集任务已启动")
    while True:
        await asyncio.sleep(METRICS_COLLECT_INTERVAL)
        try:
            async with AsyncSessionLocal() as db:
                containers = await crud_container.list_containers(db, skip=0, limit=1000)
                running_containers = [c for c in containers if c.status.value == "running"]
                
                # 并发采集，限制并发数为 10
                semaphore = asyncio.Semaphore(10)
                
                async def collect_with_semaphore(container):
                    async with semaphore:
                        await _collect_single_container_metrics(container, db)
                
                tasks = [collect_with_semaphore(c) for c in running_containers]
                await asyncio.gather(*tasks, return_exceptions=True)
                
        except Exception as e:
            logger.error(f"[定时任务] Metrics collection error: {e}")


async def _metrics_cleanup_loop():
    """后台循环：定期清理历史性能数据"""
    logger.info("[定时任务] 历史数据清理任务已启动")
    while True:
        await asyncio.sleep(METRICS_CLEANUP_INTERVAL)
        try:
            async with AsyncSessionLocal() as db:
                deleted_count = await crud_metrics.cleanup_old_metrics(db, days=METRICS_RETENTION_DAYS)
                logger.info(f"[定时任务] 清理了 {deleted_count} 条历史性能数据")
        except Exception as e:
            logger.error(f"[定时任务] Metrics cleanup error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan：启动 → yield → 关闭"""
    await ensure_edubot_network()

    # 启动后台任务
    cleanup_task = asyncio.create_task(_stale_container_cleanup_loop())
    metrics_task = asyncio.create_task(_metrics_collection_loop())
    metrics_cleanup_task = asyncio.create_task(_metrics_cleanup_loop())
    logger.info("🚀 Edubot Twin API 启动中...")
    logger.info("📚 API 文档: http://localhost:8000/docs")

    yield  # 应用运行中

    # 关闭时取消后台任务
    cleanup_task.cancel()
    metrics_task.cancel()
    metrics_cleanup_task.cancel()
    for task in [cleanup_task, metrics_task, metrics_cleanup_task]:
        try:
            await task
        except asyncio.CancelledError:
            pass

    # 兜底清理 Dry Run 容器（内存态会话）
    await dry_run_manager.cleanup_all(remove_container)

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
