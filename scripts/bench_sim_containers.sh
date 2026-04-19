#!/usr/bin/env bash
# 仿真容器性能压测入口脚本
#
# 用法：
#   EXAM_ID=1 bash scripts/bench_sim_containers.sh [--step 2] [--max 30] [--stabilize 30]
#   bash scripts/bench_sim_containers.sh 1 [--step 2] [--max 30]
#
# 选项（透传给 Python 脚本）：
#   --step N         每轮新增容器组数（默认 2）
#   --max N          最大测试组数（默认 30）
#   --stabilize N    每轮稳定等待秒数（默认 30）
#   --cpu-threshold  主机 CPU 停止阈值 %（默认 85）
#   --mem-threshold  主机内存停止阈值 %（默认 85）
#   --api-base       后端地址（默认 http://localhost:8000/api/v1）
#   --no-cleanup     测试结束后保留容器（调试用）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# 解析第一个位置参数作为 EXAM_ID（若未通过环境变量提供）
if [[ "${1:-}" =~ ^[0-9]+$ ]]; then
    EXAM_ID="$1"
    shift
fi

EXAM_ID="${EXAM_ID:-}"
if [ -z "$EXAM_ID" ]; then
    echo "用法: EXAM_ID=<考试ID> bash scripts/bench_sim_containers.sh [选项]"
    echo "  或: bash scripts/bench_sim_containers.sh <考试ID> [选项]"
    echo ""
    echo "选项:"
    echo "  --step N         每轮新增容器组数（默认 2）"
    echo "  --max N          最大测试组数（默认 30）"
    echo "  --stabilize N    每轮稳定等待秒数（默认 30）"
    echo "  --cpu-threshold  CPU 阈值 %（默认 85）"
    echo "  --mem-threshold  内存阈值 %（默认 85）"
    echo "  --no-cleanup     测试后保留容器（调试用）"
    exit 1
fi

# 定位 Python 虚拟环境
if [ -f "$PROJECT_ROOT/.venv/bin/python" ]; then
    VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
elif [ -f "$PROJECT_ROOT/../.venv/bin/python" ]; then
    VENV_PYTHON="$PROJECT_ROOT/../.venv/bin/python"
else
    echo "错误：未找到 Python 虚拟环境（.venv/bin/python）"
    echo "请先创建虚拟环境：python3 -m venv .venv"
    exit 1
fi

exec "$VENV_PYTHON" "$SCRIPT_DIR/bench_sim_containers.py" --exam-id "$EXAM_ID" "$@"
