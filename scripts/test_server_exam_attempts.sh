#!/usr/bin/env bash
set -euo pipefail

# 后端考试尝试回归测试脚本
# 使用方式：bash scripts/test_server_exam_attempts.sh

cd edubot-twin-server
../.venv/bin/python -m pytest tests/test_exam_attempts.py -q
 