#!/usr/bin/env bash
# migrate_db.sh — SQLite 增量迁移脚本
#
# 用法（从项目根执行）：
#   bash scripts/migrate_db.sh
#
# 职责：对已有的 edubot.db 补加新列/索引，保持幂等（已存在则跳过）。
# init_db.py 只负责建表，本脚本负责已有表的 ALTER TABLE。

set -euo pipefail

# 服务固定从 edubot-twin-server/ 启动，数据库始终是这个文件
DB="edubot-twin-server/edubot.db"
if [ ! -f "$DB" ]; then
  echo "❌ 未找到 $DB，请先在 edubot-twin-server/ 目录下运行 init_db.py"
  exit 1
fi

echo "📦 目标数据库: $DB"

.venv/bin/python - "$DB" <<'PYEOF'
import sys, sqlite3

db_path = sys.argv[1]
conn = sqlite3.connect(db_path)
cur = conn.cursor()


def has_column(table: str, column: str) -> bool:
    cur.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def add_column(table: str, column: str, typedef: str):
    if has_column(table, column):
        print(f"  ⏭  {table}.{column} 已存在，跳过")
    else:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {typedef}")
        print(f"  ✅ 已添加 {table}.{column}")


# ─── 第13期新增字段 ─────────────────────────────────────────────────────────
print("\n[第13期] exam_attempts 补列")
add_column("exam_attempts", "breakdown_json",  "TEXT DEFAULT NULL")

# ─── 未来新期次在此追加 ─────────────────────────────────────────────────────
# add_column("exam_attempts", "new_field", "TEXT DEFAULT NULL")

conn.commit()
conn.close()
print("\n✅ 迁移完成")
PYEOF
