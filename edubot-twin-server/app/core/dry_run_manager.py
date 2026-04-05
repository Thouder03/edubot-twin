"""
Dry Run 容器会话管理器。

设计目标：
1. 仅保存在内存中，进程退出即丢失（满足“退出即清理”约束）
2. 提供注册 / 查询 / 注销 / 批量清理能力
3. 与 API 解耦，便于在 lifespan 或异常分支统一兜底清理
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class DryRunSession:
    """单个 Dry Run 会话记录。"""

    container_id: str
    env_bundle_id: int
    teacher_id: int
    gzbridge_port: int
    rosbridge_port: int
    created_at: datetime


class DryRunManager:
    """进程内 Dry Run 会话注册表。"""

    def __init__(self) -> None:
        self._sessions: dict[str, DryRunSession] = {}

    def register(self, session: DryRunSession) -> None:
        self._sessions[session.container_id] = session
        logger.info(
            "[dry_run.register] container_id=%s env_bundle_id=%s teacher_id=%s",
            session.container_id,
            session.env_bundle_id,
            session.teacher_id,
        )

    def get(self, container_id: str) -> Optional[DryRunSession]:
        return self._sessions.get(container_id)

    def unregister(self, container_id: str) -> Optional[DryRunSession]:
        session = self._sessions.pop(container_id, None)
        if session:
            logger.info(
                "[dry_run.unregister] container_id=%s env_bundle_id=%s teacher_id=%s",
                session.container_id,
                session.env_bundle_id,
                session.teacher_id,
            )
        return session

    def list_container_ids(self) -> list[str]:
        return list(self._sessions.keys())

    async def cleanup_all(
        self,
        remover: Callable[[str], Awaitable[None]],
    ) -> None:
        """清理所有残留 Dry Run 容器（用于进程退出兜底）。"""

        for container_id in list(self._sessions.keys()):
            try:
                await remover(container_id)
                logger.info("[dry_run.cleanup_all] removed container_id=%s", container_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[dry_run.cleanup_all] remove failed container_id=%s error=%s",
                    container_id,
                    exc,
                )
            finally:
                self.unregister(container_id)


# 全局单例（API 与 lifespan 共用）
dry_run_manager = DryRunManager()
