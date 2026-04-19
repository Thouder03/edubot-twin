#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVER_DIR="$SCRIPT_DIR/../edubot-twin-server"
VENV="$SCRIPT_DIR/../.venv/bin"
ENV_FILE="$SERVER_DIR/.env"

# 加载 .env（支持注释行和空行）
if [ -f "$ENV_FILE" ]; then
    export $(grep -v '^\s*#' "$ENV_FILE" | grep -v '^\s*$' | xargs)
fi

cd "$SERVER_DIR"
"$VENV/uvicorn" app.main:app --host 0.0.0.0 --port 8000
