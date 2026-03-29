"""
容器生命周期管理器

所有 Docker SDK 调用（同步）通过 run_in_executor 包装为异步，
避免阻塞 FastAPI 事件循环。
"""
import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from docker.errors import NotFound, APIError

from app.core.docker_client import get_docker_client, DockerConnectionError  # noqa: F401

logger = logging.getLogger(__name__)

# 学生工作区根目录
STUDENTS_DATA_DIR = Path("data/students").resolve()
TEMPLATES_DIR = Path("data/templates/ros_packages").resolve()

# 专用线程池：Docker 操作可能耗时较长，独立于默认线程池
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="docker")


async def _run_in_executor(func, *args):
    """将同步 Docker 调用包装为异步"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, func, *args)


# ─── 学生工作区初始化 ──────────────────────────────────────

def create_student_workspace(student_id: int) -> Path:
    """
    初始化学生工作区目录结构。
    
    创建工作区及其子目录，可选复制模板文件。
    如果工作区已存在则直接返回路径。

    Args:
        student_id: 学生 ID
    
    Returns:
        工作区直径路径 (Path 对象)
    """
    workspace = STUDENTS_DATA_DIR / str(student_id) / "workspace"
    
    # 创建标准目录结构
    for subdir in ["src", "launch", "config", "scripts"]:
        (workspace / subdir).mkdir(parents=True, exist_ok=True)
    
    # 复制模板文件（可选）
    if TEMPLATES_DIR.exists():
        import shutil
        for item in TEMPLATES_DIR.iterdir():
            dest = workspace / "src" / item.name
            if not dest.exists():
                try:
                    if item.is_file():
                        shutil.copy2(item, dest)
                    elif item.is_dir():
                        shutil.copytree(item, dest)
                except OSError as e:
                    logger.warning(f"复制模板失败: {item} -> {dest}: {e}")
    
    logger.info(f"学生工作区已初始化: {workspace}")
    return workspace


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

        # 初始化学生工作区目录（第七期新增）
        try:
            workspace_path = create_student_workspace(student_id)
        except Exception as e:
            logger.error(f"学生工作区初始化失败: {e}")
            workspace_path = None

        # 构建 Volume 挂载配置（第七期新增）
        volumes = {}
        if workspace_path and workspace_path.exists():
            volumes[str(workspace_path)] = {
                "bind": "/home/student/workspace",
                "mode": "rw",
            }
            logger.info(f"工作区 Volume 挂载: {workspace_path} -> /home/student/workspace")
        
        # ROS 模板目录（只读挂载）
        templates_host = str(TEMPLATES_DIR)
        if TEMPLATES_DIR.exists():
            volumes[templates_host] = {
                "bind": "/opt/templates",
                "mode": "ro",
            }

        # 清理同名残留容器（防止 name conflict）
        try:
            old = client.containers.get(container_name)
            old.remove(force=True)
            logger.warning(f"已清理残留容器: {container_name}")
        except NotFound:
            pass

        # 临时方案，TODO: 优化
        # 准备启动命令：在启动前注入 websocket_external_port 以解决宿主机端口映射导致的 Host header 校验失败问题
        entrypoint_cmd = "/home/ubuntu20/gzweb/dev_entrypoint.sh"
        launch_file = "/home/ubuntu20/catkin_ws/src/bingda_tutorials/launch/simulation_robot.launch"
        # 使用 sed 在 rosbridge_websocket.launch 的 include 块中动态插入 websocket_external_port 参数（幂等处理）
        patch_cmd = (
            f"grep -q 'websocket_external_port' {launch_file} || "
            f"sed -i '/rosbridge_websocket.launch/,/<\/include>/ "
            f"s|<\/include>|<arg name=\"websocket_external_port\" value=\"{ros_port}\" /><\/include>|' "
            f"{launch_file}"
        )
        
        container = client.containers.run(
            image=image,
            detach=True,
            name=container_name,
            entrypoint="/bin/bash",                             # 临时方案，TODO: 优化
            command=["-c", f"{patch_cmd} && {entrypoint_cmd}"], # 临时方案，TODO: 优化
            ports={
                "8080/tcp": gz_port,
                "9090/tcp": ros_port,
            },
            volumes=volumes,          # 第七期新增：Volume 挂载
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


# ─── 容器性能数据获取 ─────────────────────────────────────────────

@dataclass
class ContainerStats:
    """容器实时性能数据"""
    cpu_percent: float
    memory_usage: int    # bytes
    memory_limit: int    # bytes


async def get_container_stats(container_id: str) -> Optional[ContainerStats]:
    """
    获取容器实时 CPU / 内存性能数据

    使用 docker-py 的 stats(stream=False) 获取单次快照。
    CPU 百分比使用 Docker 官方算法计算：
        cpu_delta = cpu_total - pre_cpu_total
        system_delta = system_cpu - pre_system_cpu
        cpu_percent = (cpu_delta / system_delta) * num_cpus * 100

    Returns:
        ContainerStats 实例，容器不存在或非 running 时返回 None
    """
    def _sync() -> Optional[ContainerStats]:
        client = get_docker_client()
        try:
            container = client.containers.get(container_id)
            raw = container.stats(stream=False)

            # CPU 计算
            cpu_delta = (
                raw["cpu_stats"]["cpu_usage"]["total_usage"]
                - raw["precpu_stats"]["cpu_usage"]["total_usage"]
            )
            system_delta = (
                raw["cpu_stats"].get("system_cpu_usage", 0)
                - raw["precpu_stats"].get("system_cpu_usage", 0)
            )
            num_cpus = raw["cpu_stats"].get("online_cpus") or len(
                raw["cpu_stats"]["cpu_usage"].get("percpu_usage", [1])
            )
            if system_delta > 0 and cpu_delta >= 0:
                cpu_percent = (cpu_delta / system_delta) * num_cpus * 100.0
            else:
                cpu_percent = 0.0

            # 内存
            mem_stats = raw.get("memory_stats", {})
            memory_usage = mem_stats.get("usage", 0)
            memory_limit = mem_stats.get("limit", 2 * 1024 ** 3)  # 默认 2GB

            return ContainerStats(
                cpu_percent=round(cpu_percent, 1),
                memory_usage=memory_usage,
                memory_limit=memory_limit,
            )
        except (NotFound, KeyError, ZeroDivisionError) as e:
            logger.debug(f"get_container_stats({container_id}) 异常: {e}")
            return None

    return await _run_in_executor(_sync)
