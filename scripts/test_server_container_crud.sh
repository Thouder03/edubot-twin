#!/usr/bin/env bash
set -euo pipefail

# 容器 CRUD 回归测试脚本
# 使用方式：bash scripts/test_server_container_crud.sh

cd edubot-twin-server
../.venv/bin/python -m pytest tests/test_container_crud.py -q
