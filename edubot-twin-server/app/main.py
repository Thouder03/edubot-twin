import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.api import api_router
from app.db.database import engine, AsyncSessionLocal
from app.db.base import Base
from app.crud import container as crud_container
from app.crud import container_metrics as crud_metrics
from app.crud import simulation_task as crud_simulation_task
from app.schemas.container_metrics import ContainerMetricsCreate
from app.core.logger import log_container_event
from app.core.container_manager import (
    ensure_edubot_network,
    remove_container,
    inspect_container,
    inspect_container_state,
    list_edubot_simulation_containers,
)
from app.models.container import ContainerStatus
from app.core.sidecar_timeout_scanner import sidecar_timeout_scanner_loop

logger = logging.getLogger(__name__)

# ─── 定时任务参数 ────────────────────────────────────────
STALE_CHECK_INTERVAL = 60    # 每 60 秒扫描一次
HEARTBEAT_TIMEOUT = 120      # 心跳超时阈值：2 分钟
METRICS_COLLECT_INTERVAL = 10  # 每 10 秒采集一次性能指标
METRICS_CLEANUP_INTERVAL = 86400  # 每 24 小时清理一次历史数据
METRICS_RETENTION_DAYS = 7   # 保留 7 天的历史数据

# ─── 孤儿容器自洗参数 ────────────────────────────────────
ORPHAN_RECONCILE_INTERVAL = 300   # 每 5 分钟扫描一次
ZOMBIE_STATE_TIMEOUT = 600        # CREATING/STOPPING/REMOVING 超 10 分钟视为僵死
ORPHAN_GRACE_SECONDS = 60         # 物理容器创建 60 秒内不视为孤儿（给 DB 落库留窗口）


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


# ─── 孤儿容器自洗（双向 reconcile） ────────────────────────
async def _orphan_container_reconcile_once() -> dict[str, int]:
    """
    执行一次完整的孤儿容器 reconcile（三阶段）。

    阶段 A — DB 状态僵死回收：处理 CREATING/STOPPING/REMOVING 长期未推进
    阶段 B — DB → Docker 校准：活跃记录探活，修正失配状态
    阶段 C — Docker → DB 反向清洗：物理孤儿容器强制删除

    Returns:
        {"zombie_recovered": int, "db_corrected": int, "physical_removed": int}
    """
    stats = {"zombie_recovered": 0, "db_corrected": 0, "physical_removed": 0}

    async with AsyncSessionLocal() as db:
        # ── 阶段 A：状态僵死回收 ─────────────────────────────
        try:
            zombies = await crud_container.find_zombie_state_containers(
                db, timeout_seconds=ZOMBIE_STATE_TIMEOUT
            )
        except Exception as e:
            logger.error(f"[孤儿清洗] 阶段 A 查询失败: {e}")
            zombies = []

        for c in zombies:
            try:
                state = (
                    await inspect_container_state(c.container_id)
                    if c.container_id
                    else None
                )
                if state is None:
                    # Docker 中已不存在（含 container_id 为空的情况）：DB 直接删除释放端口
                    log_container_event(
                        event_type="orphan_reconcile",
                        container_id=c.id,
                        student_id=c.user_id,
                        message=(
                            f"zombie {c.status.value} 状态记录回收"
                            f"（docker 已不存在）"
                        ),
                        level="WARNING",
                    )
                    await db.delete(c)
                    stats["zombie_recovered"] += 1
                elif state.get("status") == "running":
                    # 罕见：状态卡 STOPPING 但 docker 实际在跑，恢复为 RUNNING
                    c.status = ContainerStatus.RUNNING
                    c.error_message = None
                    c.last_heartbeat_at = datetime.utcnow()
                    c.updated_at = datetime.utcnow()
                    log_container_event(
                        event_type="orphan_reconcile",
                        container_id=c.id,
                        student_id=c.user_id,
                        message="zombie 状态校准为 RUNNING（docker 实际在跑）",
                        level="WARNING",
                    )
                    stats["zombie_recovered"] += 1
                else:
                    # exited / dead / created：强制删除 + 清 DB
                    try:
                        await remove_container(c.container_id, force=True)
                    except Exception as re:
                        logger.error(
                            f"[孤儿清洗] 阶段 A remove {c.container_id} 失败: {re}"
                        )
                    log_container_event(
                        event_type="orphan_reconcile",
                        container_id=c.id,
                        student_id=c.user_id,
                        message=(
                            f"zombie {c.status.value} 记录回收"
                            f"（docker 状态={state.get('status')}）"
                        ),
                        level="WARNING",
                    )
                    await db.delete(c)
                    stats["zombie_recovered"] += 1
            except Exception as e:
                logger.error(f"[孤儿清洗] 阶段 A 处理 container id={c.id} 失败: {e}")

        try:
            await db.commit()
        except Exception as e:
            logger.error(f"[孤儿清洗] 阶段 A commit 失败: {e}")
            await db.rollback()

        # ── 阶段 B：DB → Docker 校准 ────────────────────────
        try:
            active = await crud_container.find_db_containers(db)
        except Exception as e:
            logger.error(f"[孤儿清洗] 阶段 B 查询失败: {e}")
            active = []

        for c in active:
            try:
                docker_status = await inspect_container(c.container_id)
                if docker_status is None:
                    # 物理容器已不存在：直接删除 DB 孤儿记录，避免列表长期残留“幽灵容器”
                    orphan_db_id = c.id
                    orphan_user_id = c.user_id
                    orphan_container_id = c.container_id
                    await db.delete(c)
                    log_container_event(
                        event_type="orphan_reconcile",
                        container_id=orphan_db_id,
                        student_id=orphan_user_id,
                        message=(
                            "DB 孤儿记录已清理（docker 已无此容器）"
                            f" docker_id={orphan_container_id}"
                        ),
                        level="WARNING",
                    )
                    stats["db_corrected"] += 1
                elif docker_status in ("exited", "dead"):
                    c.status = ContainerStatus.STOPPED
                    c.updated_at = datetime.utcnow()
                    log_container_event(
                        event_type="orphan_reconcile",
                        container_id=c.id,
                        student_id=c.user_id,
                        message=f"DB 状态校准为 STOPPED（docker={docker_status}）",
                        level="INFO",
                    )
                    stats["db_corrected"] += 1
                # running / created / paused / restarting：保持不动
            except Exception as e:
                logger.error(
                    f"[孤儿清洗] 阶段 B 处理 container id={c.id} 失败: {e}"
                )

        try:
            await db.commit()
        except Exception as e:
            logger.error(f"[孤儿清洗] 阶段 B commit 失败: {e}")
            await db.rollback()

        # ── 阶段 C：Docker → DB 反向清洗 ────────────────────
        try:
            physical = await list_edubot_simulation_containers()
            known_ids = await crud_container.get_known_container_ids(db)
            now = datetime.utcnow()
            grace = timedelta(seconds=ORPHAN_GRACE_SECONDS)
            for item in physical:
                if item["short_id"] in known_ids:
                    continue
                if now - item["created_at"] < grace:
                    continue  # 宽限期内，可能 DB 还没落库
                try:
                    await remove_container(item["short_id"], force=True)
                    log_container_event(
                        event_type="orphan_reconcile",
                        message=(
                            f"物理孤儿容器已清理: {item['name']} "
                            f"({item['short_id']})"
                        ),
                        level="WARNING",
                        extra={
                            "docker_status": item["status"],
                            "labels": item["labels"],
                        },
                    )
                    stats["physical_removed"] += 1
                except Exception as re:
                    logger.error(
                        f"[孤儿清洗] 阶段 C 删除 {item['short_id']} 失败: {re}"
                    )
        except Exception as e:
            logger.error(f"[孤儿清洗] 阶段 C 列表获取失败: {e}")

    if any(stats.values()):
        logger.warning(f"[孤儿清洗] 完成 reconcile: {stats}")
    return stats


async def _orphan_container_reconcile_loop():
    """后台循环：定期执行孤儿容器 reconcile（双向校准 + 物理清洗）"""
    logger.info("[定时任务] 孤儿容器 reconcile 任务已启动")
    while True:
        await asyncio.sleep(ORPHAN_RECONCILE_INTERVAL)
        try:
            await _orphan_container_reconcile_once()
        except Exception as e:
            logger.error(f"[定时任务] 孤儿 reconcile 异常: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan：启动 → yield → 关闭"""
    await ensure_edubot_network()

    # 启动时回收孤儿任务：开发环境 reload 会中断后台协程，所有活跃任务均应标记失败可重试
    try:
        async with AsyncSessionLocal() as db:
            recovered = await crud_simulation_task.recover_orphan_tasks(db, stale_minutes=0)
            if recovered:
                logger.warning("[启动自愈] 已回收孤儿仿真任务 %s 条", recovered)
            else:
                logger.info("[启动自愈] 未发现孤儿仿真任务")
    except Exception as e:
        logger.error("[启动自愈] 孤儿任务回收失败: %s", e)

    # 启动期主动执行一次孤儿容器 reconcile：
    # 覆盖宿主机意外重启 / Docker Daemon 被 kill -9 / reload 中断删除链路等场景
    try:
        orphan_stats = await _orphan_container_reconcile_once()
        if any(orphan_stats.values()):
            logger.warning("[启动自愈] 孤儿容器 reconcile 完成: %s", orphan_stats)
        else:
            logger.info("[启动自愈] 未发现孤儿容器")
    except Exception as e:
        logger.error("[启动自愈] 孤儿容器 reconcile 失败: %s", e)

    # 启动后台任务
    cleanup_task = asyncio.create_task(_stale_container_cleanup_loop())
    metrics_task = asyncio.create_task(_metrics_collection_loop())
    metrics_cleanup_task = asyncio.create_task(_metrics_cleanup_loop())
    orphan_task = asyncio.create_task(_orphan_container_reconcile_loop())
    # 第12期：Sidecar 超时扫描任务
    sidecar_scanner_task = asyncio.create_task(sidecar_timeout_scanner_loop())
    logger.info("🚀 Edubot Twin API 启动中...")
    logger.info("📚 API 文档: http://localhost:8000/docs")

    yield  # 应用运行中

    # 关闭时取消后台任务
    cleanup_task.cancel()
    metrics_task.cancel()
    metrics_cleanup_task.cancel()
    orphan_task.cancel()
    sidecar_scanner_task.cancel()
    for task in [cleanup_task, metrics_task, metrics_cleanup_task, orphan_task, sidecar_scanner_task]:
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
        reload=True,
        reload_excludes=[
            "data/*",
            "data/students/*",
            "data/students/**/*",
            "edubot-twin-server/data/students/*",
            "edubot-twin-server/data/*",
            "edubot-twin-server/data/students/**/*",
        ],
    )
