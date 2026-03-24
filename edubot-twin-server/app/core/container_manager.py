"""
容器生命周期管理器

所有 Docker SDK 调用（同步）通过 run_in_executor 包装为异步，
避免阻塞 FastAPI 事件循环。
"""
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from docker.errors import NotFound, APIError

from app.core.docker_client import get_docker_client, DockerConnectionError  # noqa: F401

logger = logging.getLogger(__name__)

# 专用线程池：Docker 操作可能耗时较长，独立于默认线程池
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="docker")


async def _run_in_executor(func, *args):
    """将同步 Docker 调用包装为异步"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, func, *args)


# ─── 容器创建 ───────────────────────────────────────────────

async def create_container(
    image: str,
    student_id: int,
    gz_port: int,
    ros_port: int,
) -> str:
    """
    创建并启动 Docker 容器

    Args:
        image: 镜像名 (如 gzweb_sim:v1)
        student_id: 学生 ID（用于容器命名和标签）
        gz_port: 宿主机 gzbridge 映射端口
        ros_port: 宿主机 rosbridge 映射端口

    Returns:
        容器 short_id (12 位 hex)

    Raises:
        DockerConnectionError: Docker 不可达
        APIError: 容器创建失败（如端口冲突、镜像不存在）
    """
    def _sync():
        client = get_docker_client()
        container_name = f"edubot-sim-{student_id}"

        # 清理同名残留容器（防止 name conflict）
        try:
            old = client.containers.get(container_name)
            old.remove(force=True)
            logger.warning(f"已清理残留容器: {container_name}")
        except NotFound:
            pass

        container = client.containers.run(
            image=image,
            detach=True,
            name=container_name,
            ports={
                "8080/tcp": gz_port,
                "9090/tcp": ros_port,
            },
            mem_limit="2g",
            nano_cpus=2_000_000_000,  # 2 CPU cores
            labels={
                "edubot.student_id": str(student_id),
                "edubot.type": "simulation",
            },
            remove=False,
        )
        return container.short_id

    return await _run_in_executor(_sync)


# ─── 容器启动 ───────────────────────────────────────────────

async def start_container(container_id: str) -> None:
    """启动已停止的容器"""
    def _sync():
        client = get_docker_client()
        container = client.containers.get(container_id)
        container.start()

    await _run_in_executor(_sync)


# ─── 容器停止 ───────────────────────────────────────────────

async def stop_container(container_id: str, timeout: int = 10) -> None:
    """
    停止运行中的容器

    Args:
        container_id: Docker 容器 ID
        timeout: 等待优雅退出的秒数，超时后 SIGKILL
    """
    def _sync():
        client = get_docker_client()
        container = client.containers.get(container_id)
        container.stop(timeout=timeout)

    await _run_in_executor(_sync)


# ─── 容器删除 ───────────────────────────────────────────────

async def remove_container(container_id: str, force: bool = True) -> None:
    """删除容器"""
    def _sync():
        client = get_docker_client()
        try:
            container = client.containers.get(container_id)
            container.remove(force=force)
        except NotFound:
            logger.info(f"容器 {container_id} 已不存在，跳过删除")

    await _run_in_executor(_sync)


# ─── 容器状态查询 ─────────────────────────────────────────────

async def inspect_container(container_id: str) -> Optional[str]:
    """
    查询容器运行状态

    Returns:
        Docker 原生状态字符串 ('running', 'exited', 'created', 'dead', 等)
        容器不存在时返回 None
    """
    def _sync():
        client = get_docker_client()
        try:
            container = client.containers.get(container_id)
            container.reload()
            return container.status
        except NotFound:
            return None

    return await _run_in_executor(_sync)
