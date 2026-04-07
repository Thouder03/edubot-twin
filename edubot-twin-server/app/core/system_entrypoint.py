"""
system_entrypoint — 系统常驻启动脚本管理（10-S1-7b）

负责生成和挂载 system_entrypoint.sh。
该脚本是容器唯一前台入口，统一拉起教师自定义 startup.sh、rosbridge、gzweb，
并定义任一关键进程退出时的失败语义和清理动作。

参考：/home/ubuntu20/gzweb/dev_entrypoint.sh
约束：不允许"教师脚本后台启动 + 系统脚本再各自拉起服务"的松耦合模式。
"""
import logging
import os
import stat
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 系统常驻启动脚本存放目录（宿主机，平台维护）
SYSTEM_SCRIPTS_DIR = Path("data/system").resolve()
SYSTEM_ENTRYPOINT_PATH = SYSTEM_SCRIPTS_DIR / "system_entrypoint.sh"

# 教师启动脚本在容器内的固定挂载路径
CONTAINER_STARTUP_SCRIPT = "/tmp/startup.sh"
# 系统常驻启动脚本在容器内的固定挂载路径
CONTAINER_SYSTEM_ENTRYPOINT = "/tmp/system_entrypoint.sh"

# Sidecar 文件服务宿主机路径和容器内路径
SIDECAR_SCRIPT_HOST = Path("data/system/agent/mini_file_server.py").resolve()
SIDECAR_SCRIPT_CONTAINER = "/opt/edubot/agent/mini_file_server.py"
# Sidecar 监听端口（容器内，仅 Docker bridge 网络可达）
SIDECAR_PORT = 8010

# startup.sh 模板内容（10-S1-3: 启动脚本以文件形式存储在环境包根目录）
STARTUP_SCRIPT_TEMPLATE = """\
#!/bin/bash
# ================================================================
# 教师启动脚本 — 以 ROOT 权限执行
# ================================================================
# 本脚本在容器启动时首先执行，用于：
#   1. 加载 ROS 环境
#   2. 启动仿真节点（roslaunch）
#
# 注意：rosbridge 和 gzweb 由系统常驻脚本自动启动，无需在此处理。
#
# 常用模板（请根据实际情况修改）：
# ================================================================

# ── 1. 设置工作空间路径 ──────────────────────────────────────
WORKSPACE=/home/ubuntu20/catkin_ws

# ── 2. 加载 ROS 环境 ────────────────────────────────────────
source "/opt/ros/noetic/setup.bash"
source "$WORKSPACE/devel/setup.bash"

# ── 3. 设置并同步 Gazebo 自定义模型（可选：有自建模型时取消注释）──
# CUSTOM_MODEL_DIR="$WORKSPACE/src/your_package/models"
# export GAZEBO_MODEL_PATH=$GAZEBO_MODEL_PATH:$CUSTOM_MODEL_DIR
#
# if [ -d "$CUSTOM_MODEL_DIR" ]; then
#     echo "正在同步自定义模型至浏览器前端 (GzWeb)..."
#     cp -r $CUSTOM_MODEL_DIR/* /home/ubuntu20/gzweb/http/client/assets/
#
#     # 对自建模型增量转换 Web 格式 (PNG 贴图与路径修复)
#     for model_path in $CUSTOM_MODEL_DIR/*; do
#         if [ -d "$model_path" ]; then
#             TARGET_ASSET="/home/ubuntu20/gzweb/http/client/assets/$(basename "$model_path")"
#             python3 /home/ubuntu20/gzweb/webify_models_v2.py "$TARGET_ASSET" || true
#         fi
#     done
# fi

# ── 4. 启动 ROS 仿真节点（后台运行）──────────────────────────
# $LAUNCH_ARGS 由平台自动注入版本配置中的 launch_args_template 参数
# 例如: launch_args_template = {"robot_model": "turtlebot3", "world": "maze"}
#       → LAUNCH_ARGS="robot_model:=turtlebot3 world:=maze"
# roslaunch your_package your_launch_file.launch $LAUNCH_ARGS &

# ── 5. 等待仿真启动 ──────────────────────────────────────────
# sleep 5
"""

# system_entrypoint.sh 模板（统一前台守护入口，参考 dev_entrypoint.sh）
SYSTEM_ENTRYPOINT_TEMPLATE = """\
#!/bin/bash
# ============================================================
# system_entrypoint.sh — 系统常驻启动脚本（平台自动挂载，教师不可修改）
# 功能：统一前台守护入口，拉起教师 startup.sh、rosbridge、gzweb、Sidecar
# 端口通过环境变量注入：ROSBRIDGE_PORT, GZWEB_PORT
# LAUNCH_ARGS 由平台注入版本配置中的 launch_args_template 参数
# ============================================================

ROSBRIDGE_PORT=${ROSBRIDGE_PORT:-9090}
GZWEB_PORT=${GZWEB_PORT:-8080}
GZWEB_DIR=${GZWEB_DIR:-/home/ubuntu20/gzweb}
WORKSPACE=/home/ubuntu20/catkin_ws

source "/opt/ros/noetic/setup.bash"
source "$WORKSPACE/devel/setup.bash"

# ── 1. 执行教师自定义启动脚本（source 环境 + roslaunch）────────
if [ -f "/tmp/startup.sh" ]; then
    echo "[system_entrypoint] 正在执行教师启动脚本 /tmp/startup.sh ..."
    chmod +x /tmp/startup.sh
    bash /tmp/startup.sh
    echo "[system_entrypoint] 教师启动脚本执行完成"
else
    echo "[system_entrypoint] 未挂载教师启动脚本，跳过"
fi

# ── 2. 启动 mini_file_server Sidecar（后台运行，仅 Docker bridge 可达）──
SIDECAR_SCRIPT="/opt/edubot/agent/mini_file_server.py"
if [ -f "$SIDECAR_SCRIPT" ]; then
    echo "[system_entrypoint] 正在启动文件服务 Sidecar (port=8010)..."
    mkdir -p /opt/edubot/agent
    python3 -m uvicorn mini_file_server:app --host 0.0.0.0 --port 8010 --app-dir /opt/edubot/agent &
    SIDECAR_PID=$!
    echo "[system_entrypoint] Sidecar 已启动 (PID=$SIDECAR_PID)"
else
    echo "[system_entrypoint] 未挂载 Sidecar 脚本，跳过"
    SIDECAR_PID=""
fi

# ── 3. 启动 rosbridge_server（后台运行）─────────────────────
echo "[system_entrypoint] 正在启动 rosbridge (port=${ROSBRIDGE_PORT})..."
roslaunch rosbridge_server rosbridge_websocket.launch port:=${ROSBRIDGE_PORT} &
ROSBRIDGE_PID=$!
sleep 2

# ── 4. 启动 gzweb（后台运行）────────────────────────────────
echo "[system_entrypoint] 正在启动 gzweb (port=${GZWEB_PORT})..."
cd $GZWEB_DIR
GZWEB_PORT=${GZWEB_PORT} npm start &
GZWEB_PID=$!

# ── 5. 等待任一关键进程退出，容器进入失败态 ──────────────────
wait -n $ROSBRIDGE_PID $GZWEB_PID
EXIT_CODE=$?
echo "[system_entrypoint] 关键进程退出（exit_code=${EXIT_CODE}），容器即将终止"
kill $ROSBRIDGE_PID $GZWEB_PID $SIDECAR_PID 2>/dev/null
exit $EXIT_CODE
"""


def ensure_system_entrypoint() -> Path:
    """
    确保系统常驻启动脚本存在且为最新版本。
    始终写入最新模板（幂等），保证 Sidecar 等新功能生效。

    :returns: 脚本文件的绝对路径
    """
    SYSTEM_SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

    SYSTEM_ENTRYPOINT_PATH.write_text(SYSTEM_ENTRYPOINT_TEMPLATE, encoding="utf-8")
    SYSTEM_ENTRYPOINT_PATH.chmod(
        SYSTEM_ENTRYPOINT_PATH.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    )
    logger.debug(f"系统常驻启动脚本已同步: {SYSTEM_ENTRYPOINT_PATH}")

    return SYSTEM_ENTRYPOINT_PATH


def create_env_bundle_startup_script(storage_root: str) -> None:
    """
    为新建的环境包自动生成 startup.sh 模板文件（10-S1-4）。

    :param storage_root: 环境包存储根目录
    """
    root = Path(storage_root)
    root.mkdir(parents=True, exist_ok=True)
    startup_path = root / "startup.sh"

    if not startup_path.exists():
        startup_path.write_text(STARTUP_SCRIPT_TEMPLATE, encoding="utf-8")
        startup_path.chmod(
            startup_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        )
        logger.info(f"环境包 startup.sh 模板已创建: {startup_path}")


def get_system_entrypoint_volume() -> tuple[str, str]:
    """
    获取系统常驻脚本的宿主机路径和容器内挂载路径。
    用于构建 Docker volumes 配置。

    :returns: (host_path, container_path)
    """
    host_path = str(ensure_system_entrypoint())
    return host_path, CONTAINER_SYSTEM_ENTRYPOINT


def get_sidecar_volume() -> Optional[tuple[str, str]]:
    """
    获取 Sidecar 文件服务脚本的宿主机路径和容器内挂载路径。
    若脚本文件不存在则返回 None（宽容降级）。

    :returns: (host_path, container_path) 或 None
    """
    if not SIDECAR_SCRIPT_HOST.exists():
        logger.warning(f"Sidecar 脚本不存在: {SIDECAR_SCRIPT_HOST}，跳过挂载")
        return None
    return str(SIDECAR_SCRIPT_HOST), SIDECAR_SCRIPT_CONTAINER
