"""
Sidecar 超时扫描后台定时任务（第12期 S12 + §7.5）

每 10 秒扫描一次：
  1. status=running AND started_at + max_duration_ms + 30s < now → 强制终止
  2. status=pending AND created_at + PENDING_STALE_MINUTES < now → 标记 stale（可重试）

由 app/main.py 在 lifespan 中启动：asyncio.create_task(sidecar_timeout_scanner_loop())
"""

import asyncio
import logging

from app.crud import exam_attempt as crud_attempt
from app.core.sidecar_manager import kill_timeout_sidecar
from app.db.database import AsyncSessionLocal
from app.models.exam_attempt import ExamAttemptStatus, EvidenceEventType

logger = logging.getLogger(__name__)

# 扫描间隔（秒）
SCAN_INTERVAL = 10

# pending 超时回收阈值（分钟），与 crud 中保持一致
PENDING_STALE_MINUTES = 10


async def _scan_timeout_running() -> None:
    """扫描并终止超时的 running attempt"""
    async with AsyncSessionLocal() as db:
        timeout_attempts = await crud_attempt.find_timeout_running_attempts(db)
        for attempt in timeout_attempts:
            logger.warning(
                f"[超时扫描] attempt={attempt.id} 已超时，触发强制终止"
            )
            try:
                await kill_timeout_sidecar(attempt.id)
            except Exception as e:
                logger.error(f"[超时扫描] kill attempt={attempt.id} 失败: {e}")


async def _scan_stale_pending() -> None:
    """扫描并回收超时未启动的 pending attempt"""
    async with AsyncSessionLocal() as db:
        stale_attempts = await crud_attempt.find_stale_pending_attempts(
            db, stale_minutes=PENDING_STALE_MINUTES
        )
        for attempt in stale_attempts:
            logger.warning(
                f"[超时扫描] attempt={attempt.id} pending 超时，标记为 error（可重试）"
            )
            try:
                await crud_attempt.record_event(
                    db, attempt_id=attempt.id,
                    event_type=EvidenceEventType.SYSTEM_WARNING,
                    payload={
                        "code": "ATTEMPT_PENDING_STALE",
                        "message": f"pending 状态超过 {PENDING_STALE_MINUTES} 分钟，自动回收",
                    },
                )
                attempt.status = ExamAttemptStatus.ERROR
                attempt.error_code = "ATTEMPT_PENDING_STALE"
                attempt.error_message = f"创建后 {PENDING_STALE_MINUTES} 分钟内未调用 /start，已自动回收"
                await db.commit()

                await crud_attempt.record_event(
                    db, attempt_id=attempt.id,
                    event_type=EvidenceEventType.EXAM_ATTEMPT_FINALIZED,
                    payload={"final_status": "error"},
                )
            except Exception as e:
                logger.error(f"[超时扫描] 回收 stale attempt={attempt.id} 失败: {e}")


async def sidecar_timeout_scanner_loop() -> None:
    """
    后台循环：每 SCAN_INTERVAL 秒扫描一次超时/僵尸 attempt。

    SDD §7.5：
    - status=running AND started_at + max_duration_ms + 30s < now → kill
    - status=pending AND created_at + PENDING_STALE_MINUTES < now → error
    """
    logger.info("[定时任务] Sidecar 超时扫描任务已启动（间隔 %ds）", SCAN_INTERVAL)
    while True:
        await asyncio.sleep(SCAN_INTERVAL)
        try:
            await _scan_timeout_running()
        except Exception as e:
            logger.error(f"[超时扫描] running 扫描异常: {e}")
        try:
            await _scan_stale_pending()
        except Exception as e:
            logger.error(f"[超时扫描] stale pending 扫描异常: {e}")
