#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONF="$SCRIPT_DIR/../nginx/dev.conf"

# 检查 nginx 是否已安装
if ! command -v nginx &> /dev/null; then
    echo "[错误] nginx 未安装，请先执行: sudo apt install nginx"
    exit 1
fi

# 语法检查
nginx -t -c "$CONF" 2>/dev/null || sudo nginx -t -c "$CONF"

# 停止已有实例后启动
sudo nginx -s stop 2>/dev/null || true
sudo nginx -c "$CONF"

echo "[OK] Nginx 已启动，监听 http://0.0.0.0:80"
echo "     记得先在 edubot-twin-server/.env 中设置 SERVER_HOST=<实际IP>"
