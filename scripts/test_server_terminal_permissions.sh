#!/usr/bin/env bash
set -euo pipefail

# 学生终端权限修复测试脚本
# 使用方式：bash scripts/test_server_terminal_permissions.sh

cd edubot-twin-server
../.venv/bin/python -m pytest tests/test_terminal_permissions.py -q
