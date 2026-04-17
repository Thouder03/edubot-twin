#!/usr/bin/env bash
# 修复 exam_artifacts / exam_submissions 下被 root 创建的子目录所有权
# 背景：sidecar 容器曾以 root 运行，或服务曾以 root 启动，导致目录归属 root:root
# 执行方式：sudo bash scripts/fix_exam_dir_ownership.sh

set -euo pipefail

DATA_DIR="$(cd "$(dirname "$0")/../edubot-twin-server/data" && pwd)"
TARGET_USER="${SUDO_USER:-ubuntu20}"

echo "[fix] 目标目录: $DATA_DIR"
echo "[fix] 目标用户: $TARGET_USER"

for dir in exam_artifacts exam_submissions; do
    path="$DATA_DIR/$dir"
    if [ -d "$path" ]; then
        echo "[fix] 修复 $path ..."
        chown -R "$TARGET_USER:$TARGET_USER" "$path"
        find "$path" -mindepth 1 -maxdepth 1 -type d -exec chmod 750 {} \;
        echo "[fix] 完成: $path"
    else
        echo "[skip] 目录不存在: $path"
    fi
done

echo "[fix] 全部完成"
