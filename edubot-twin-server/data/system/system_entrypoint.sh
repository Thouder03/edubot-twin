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
nice -n 10 roslaunch rosbridge_server rosbridge_websocket.launch port:=${ROSBRIDGE_PORT} &
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
