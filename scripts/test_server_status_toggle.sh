#!/usr/bin/env bash
set -euo pipefail

# 教师端实验状态切换回归测试脚本
# 使用方式：bash scripts/test_server_status_toggle.sh

cd edubot-twin-server
../.venv/bin/python -m pytest tests/test_experiment_status_toggle.py -q