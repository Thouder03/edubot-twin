#!/usr/bin/env bash
set -euo pipefail

# 第10期后端测试脚本
# 使用方式：bash scripts/test_server_phase10.sh

cd edubot-twin-server
../.venv/bin/python -m pytest tests/test_experiment_phase10.py -q
