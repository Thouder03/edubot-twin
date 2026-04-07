#!/usr/bin/env bash
# ============================================================
# Sidecar 文件服务 & 代理层测试脚本
# 使用方式：bash scripts/test_sidecar.sh
# ============================================================
set -euo pipefail

cd "$(dirname "$0")/.."

echo "=== 运行 Sidecar 与代理层测试 ==="
.venv/bin/python -m pytest \
  edubot-twin-server/tests/test_sidecar.py \
  edubot-twin-server/tests/test_container_proxy.py \
  -v --tb=short 2>&1
