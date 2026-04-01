#!/usr/bin/env bash
set -euo pipefail

# 前端 TypeScript 类型检查脚本
# 使用方式：bash scripts/ts_check_web.sh

cd edubot-twin-web
pnpm ts:check
