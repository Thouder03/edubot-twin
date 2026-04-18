"""
将数据库中存储的绝对路径迁移为相对路径（相对于 edubot-twin-server/ 目录）。

影响的字段：
  experiment_env_bundles.storage_root
  experiment_file_bundles.storage_root
  exam_env_snapshots.storage_root
  exam_file_snapshots.storage_root
  exam_eval_scripts.storage_root
  exam_attempts.submission_snapshot_path
  exam_attempts.artifacts_path

运行：从 edubot-twin-server/ 目录执行（CWD 即为 server 根目录）
  ../.venv/bin/python scripts/migrate_paths_to_relative.py [--dry-run]
"""

import argparse
import sqlite3
import sys
from pathlib import Path

# server 根目录 = 本脚本上级目录（scripts/ 的父目录）
SERVER_ROOT = Path(__file__).parent.parent.resolve()
DB_PATH = SERVER_ROOT / "edubot.db"

# 需要迁移的 (table, column) 列表
MIGRATE_TARGETS = [
    ("experiment_env_bundles",  "storage_root"),
    ("experiment_file_bundles", "storage_root"),
    ("exam_env_snapshots",      "storage_root"),
    ("exam_file_snapshots",     "storage_root"),
    ("exam_eval_scripts",       "storage_root"),
    ("exam_attempts",           "submission_snapshot_path"),
    ("exam_attempts",           "artifacts_path"),
]


def to_relative(abs_path: str) -> str:
    """将绝对路径转为相对于 SERVER_ROOT 的路径字符串。"""
    p = Path(abs_path)
    try:
        return str(p.relative_to(SERVER_ROOT))
    except ValueError:
        return abs_path  # 不属于 server root，保持原值


def migrate(dry_run: bool) -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    total_updated = 0

    for table, col in MIGRATE_TARGETS:
        # 只处理以 / 开头的绝对路径
        cur.execute(
            f"SELECT id, {col} FROM {table} WHERE {col} LIKE '/%'"
        )
        rows = cur.fetchall()
        if not rows:
            continue

        print(f"\n{table}.{col} — {len(rows)} 条记录需要迁移：")
        for row_id, old_val in rows:
            new_val = to_relative(old_val)
            print(f"  id={row_id}: {old_val!r}  →  {new_val!r}")
            if not dry_run:
                cur.execute(
                    f"UPDATE {table} SET {col} = ? WHERE id = ?",
                    (new_val, row_id),
                )
        total_updated += len(rows)

    if total_updated == 0:
        print("数据库中没有需要迁移的绝对路径，已是最新状态。")
        conn.close()
        return

    if dry_run:
        print(f"\n[DRY-RUN] 共 {total_updated} 条记录待更新，未写入数据库。")
    else:
        conn.commit()
        print(f"\n迁移完成，共更新 {total_updated} 条记录。")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="将数据库路径从绝对改为相对")
    parser.add_argument("--dry-run", action="store_true", help="仅打印变更，不修改数据库")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"错误：数据库文件不存在：{DB_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"SERVER_ROOT = {SERVER_ROOT}")
    print(f"DB_PATH     = {DB_PATH}")
    if args.dry_run:
        print("[DRY-RUN 模式，不会写入数据库]\n")

    migrate(args.dry_run)
