"""
容器生命周期管理器

所有 Docker SDK 调用（同步）通过 run_in_executor 包装为异步，
避免阻塞 FastAPI 事件循环。
"""
import asyncio
import logging
import os
import subprocess
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
EDUBOT_NETWORK = "edubot_network"

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
    
    subprocess.run(["chown", "-R", "1000:1000", str(workspace)], check=True)

    logger.info(f"学生工作区已初始化: {workspace}")
    return workspace


# ─── 网络初始化 ───────────────────────────────────────────────

async def ensure_edubot_network() -> None:
    """确保 Edubot 专用 Docker 网络存在（幂等）。"""

    def _sync():
        client = get_docker_client()

        try:
            client.networks.get(EDUBOT_NETWORK)
            return
        except NotFound:
            pass

        try:
            client.networks.create(
                EDUBOT_NETWORK,
                driver="bridge",
                check_duplicate=True,
                options={"com.docker.network.bridge.enable_icc": "false"},
            )
        except APIError as e:
            if "already exists" in str(e).lower():
                return
            raise

    await _run_in_executor(_sync)


# ─── 容器创建 ───────────────────────────────────────────────

async def create_container(
    image: str,
    student_id: int,
    gz_port: int,
    ros_port: int,
    *,
    # ── 启动配置（10-S1-7）──────────────────────────────────────────
    launch_file_path: str = "/home/ubuntu20/catkin_ws/src/bingda_tutorials/launch/simulation_robot.launch",
    launch_args: Optional[dict[str, str]] = None,
    startup_script_path: Optional[str] = None,
    # ── 文件挂载（10-S1-7）──────────────────────────────────────────
    env_volumes: Optional[dict[str, str]] = None,
    # ── 运行模式（10-S1-7）──────────────────────────────────────────
    is_dry_run: bool = False,
) -> str:
    """
    创建并启动 Docker 容器（10-S1-7 重构：动态 launch 注入 + 系统常驻入口脚本）

    按四组数据分层实现：
    1. 镜像 / 端口：image, student_id, gz_port, ros_port
    2. 启动配置：launch_file_path, launch_args, startup_script_path
    3. 文件挂载：env_volumes
    4. 运行模式：is_dry_run（标签区分正式仿真 vs Dry Run）

    :param image: 镜像名（如 gzweb_sim:v1）
    :param student_id: 学生 ID（用于容器命名和标签）
    :param gz_port: 宿主机 gzweb 映射端口
    :param ros_port: 宿主机 rosbridge 映射端口
    :param launch_file_path: ROS launch 文件路径（仅在无 startup_script_path 时作为默认 entrypoint）
    :param launch_args: launch 参数字典（格式化为 LAUNCH_ARGS 环境变量注入容器）
    :param startup_script_path: 教师自定义启动脚本宿主机路径（来自 env_bundle.storage_root/startup.sh）
    :param env_volumes: 额外 Volume 挂载映射 {host_path: container_path}（环境文件）
    :param is_dry_run: True 表示 Dry Run 试运行容器（添加 dry-run 标签，停止后立即清理）
    :returns: 容器 short_id（12 位 hex）

    向后兼容：所有新增参数有默认值，现有调用方无需修改即可继续工作。
    """
    from app.core.system_entrypoint import (
        ensure_system_entrypoint,
        CONTAINER_STARTUP_SCRIPT,
        CONTAINER_SYSTEM_ENTRYPOINT,
    )

    def _sync():
        client = get_docker_client()
        # ── 1. 镜像 / 端口配置 ─────────────────────────────────────────────────
        container_name = f"edubot-sim-{student_id}"
        if is_dry_run:
            # Dry Run 容器使用独立命名，避免与正式仿真容器冲突
            import time
            container_name = f"edubot-dryrun-{student_id}-{int(time.time())}"

        # ── 2. 启动配置：LAUNCH_ARGS 格式化 + 环境变量注入 ──────────────────────
        # launch_args 格式化为 roslaunch 参数字符串（教师 startup.sh 中通过 $LAUNCH_ARGS 引用）
        launch_args_str = (
            " ".join(f"{k}:={v}" for k, v in launch_args.items())
            if launch_args else ""
        )
        environment = {
            "ROSBRIDGE_PORT": str(ros_port),  # → 系统常驻启动脚本
            "GZWEB_PORT": str(gz_port),       # → 系统常驻启动脚本
            "LAUNCH_ARGS": launch_args_str,   # → 教师 startup.sh 中 $LAUNCH_ARGS
            "DISPLAY": ":0",
        }

        # ── 3. 文件挂载：工作区 + 系统脚本 + 教师脚本 + 环境文件 ────────────────

        # 初始化学生工作区目录
        try:
            workspace_path = create_student_workspace(student_id)
        except Exception as e:
            logger.error(f"学生工作区初始化失败: {e}")
            workspace_path = None

        volumes = {}
        # X11 显示
        volumes["/tmp/.X11-unix"] = {"bind": "/tmp/.X11-unix", "mode": "rw"}
        # 学生工作区
        if workspace_path and workspace_path.exists():
            volumes[str(workspace_path)] = {
                "bind": "/home/student/workspace",
                "mode": "rw",
            }
        # ROS 模板目录（只读）
        if TEMPLATES_DIR.exists():
            volumes[str(TEMPLATES_DIR)] = {"bind": "/opt/templates", "mode": "ro"}

        # 系统常驻启动脚本（10-S1-7b）
        system_entrypoint_host = str(ensure_system_entrypoint())
        volumes[system_entrypoint_host] = {
            "bind": CONTAINER_SYSTEM_ENTRYPOINT,
            "mode": "ro",
        }

        # 教师自定义启动脚本（来自 env_bundle.storage_root/startup.sh）
        if startup_script_path and os.path.exists(startup_script_path):
            volumes[startup_script_path] = {
                "bind": CONTAINER_STARTUP_SCRIPT,
                "mode": "ro",
            }
            logger.info(f"教师启动脚本已挂载: {startup_script_path} → {CONTAINER_STARTUP_SCRIPT}")

        # 额外环境文件 Volume（env_bundle 文件）
        if env_volumes:
            for host_path, container_path in env_volumes.items():
                volumes[host_path] = {"bind": container_path, "mode": "ro"}
                logger.info(f"环境文件 Volume 挂载: {host_path} → {container_path}")

        # ── 4. 运行模式：标签区分容器类型 ─────────────────────────────────────────
        labels = {
            "edubot.student_id": str(student_id),
            "edubot.type": "dry-run" if is_dry_run else "simulation",
        }

        # 清理同名残留容器（防止 name conflict）
        try:
            old = client.containers.get(container_name)
            old.remove(force=True)
            logger.warning(f"已清理残留容器: {container_name}")
        except NotFound:
            pass


        # 容器入口：统一前台守护入口（system_entrypoint.sh）
        # 教师自定义 startup.sh 由系统脚本内部调用（10-S1-7b）
        container = client.containers.run(
            image=image,
            detach=True,
            name=container_name,
            entrypoint="/bin/bash",
            command=["-c", f"bash {CONTAINER_SYSTEM_ENTRYPOINT}"],
            ports={
                "8080/tcp": gz_port,
                "9090/tcp": ros_port,
            },
            volumes=volumes,
            mem_limit="2g",
            nano_cpus=2_000_000_000,  # 2 CPU cores
            labels=labels,
            remove=False,
            privileged=False,
            security_opt=["no-new-privileges:true"],
            network=EDUBOT_NETWORK,
            shm_size="512m",
            devices=["/dev/dri:/dev/dri"],
            environment=environment,
        )
        logger.info(
            f"容器已创建: {container.short_id} name={container_name} "
            f"gz_port={gz_port} ros_port={ros_port} dry_run={is_dry_run}"
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
