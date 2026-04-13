"""
数据库初始化脚本：创建全部表 + 写入种子数据。

特性：
- 幂等：重复运行只补充缺失数据，不会报错或重复插入
- 完整：导入全部 ORM 模型，确保 create_all 不遗漏任何表
- 真实：种子数据与 CLAUDE.md 文档中的测试账号保持一致
"""

import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.database import AsyncSessionLocal, engine

# ── 导入全部 ORM 模型，确保 Base.metadata 包含所有表 ────────────────────────
from app.models.container import SimContainer  # noqa: F401
from app.models.container_metrics import ContainerMetrics  # noqa: F401
from app.models.experiment import (
    Experiment,
    ExperimentEnvBundle,  # noqa: F401（10-S1-4 新增模型）
    ExperimentFileBundle,  # noqa: F401
    ExperimentPublishLog,
    ExperimentStatus,
    ExperimentVersion,
    PublishStatus,
)
from app.models.exam import (  # noqa: F401（第11期新增模型）
    Exam,
    ExamEnvSnapshot,
    ExamFileSnapshot,
    ExamEvalScript,
)
from app.models.exam_attempt import (  # noqa: F401（第12期新增模型）
    ExamAttempt,
    ExamEvidenceEvent,
)
from app.models.simulation_task import SimulationTask  # noqa: F401
from app.models.student import User
from app.crud.student import hash_password

logger = logging.getLogger(__name__)

# ── 种子用户（与 CLAUDE.md §测试账号 保持一致）──────────────────────────────
SEED_USERS = [
    {"username": "admin",      "password": "admin",      "real_name": "管理员",      "role_code": "admin",   "role_id": "30"},
    {"username": "teacher",    "password": "teacher",    "real_name": "教师测试账号",   "role_code": "teacher", "role_id": "20"},
    {"username": "student",    "password": "student",    "real_name": "学生演示账号",   "role_code": "student", "role_id": "10"},
    {"username": "student001", "password": "123456",     "real_name": "张三",         "role_code": "student", "role_id": "10"},
    {"username": "student002", "password": "123456",     "real_name": "李四",         "role_code": "student", "role_id": "10"},
    {"username": "student003", "password": "123456",     "real_name": "王五",         "role_code": "student", "role_id": "10"},
    {"username": "student004", "password": "123456",     "real_name": "赵六",         "role_code": "student", "role_id": "10"},
]

# ── 种子实验（供学生端首页展示）─────────────────────────────────────────────
SEED_EXPERIMENTS = [
    {
        "name": "移动机器人基础导航实验",
        "code": "robot_basic_navigation",
        "description": "基于 TurtleBot3 的自主导航基础实验，包含 SLAM 建图与路径规划。",
        "versions": [
            {
                "version_name": "v1.0",
                "environment_key": "robot_basic_navigation_v1",
                "image_name": "gzweb_sim:v1",
                "launch_args_template": {"world_name": "turtlebot3_world"},
                "publish_status": PublishStatus.PUBLISHED,
                "publish_note": "初始发布版本",
            },
            {
                "version_name": "v1.1",
                "environment_key": "robot_basic_navigation_v1_1",
                "image_name": "gzweb_sim:v1",
                "launch_args_template": {"world_name": "turtlebot3_house"},
                "publish_status": PublishStatus.DRAFT,
                "publish_note": None,
            },
        ],
    },
]


async def _create_tables() -> None:
    print("=" * 50)
    print("  创建数据库表")
    print("=" * 50)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("  ✓ 所有表已就绪\n")


async def _seed_users(db: AsyncSession) -> dict[str, int]:
    """插入种子用户，返回 {username: id} 映射。已存在的跳过。"""
    print("=" * 50)
    print("  用户账号")
    print("=" * 50)
    user_ids: dict[str, int] = {}

    for spec in SEED_USERS:
        result = await db.execute(select(User).where(User.username == spec["username"]))
        existing = result.scalar_one_or_none()
        if existing:
            user_ids[spec["username"]] = existing.id
            print(f"  - {spec['username']:<12} 已存在，跳过")
            continue

        user = User(
            username=spec["username"],
            password_hash=hash_password(spec["password"]),
            real_name=spec["real_name"],
            role_id=spec["role_id"],
            role_code=spec["role_code"],
        )
        db.add(user)
        await db.flush()
        user_ids[spec["username"]] = user.id
        print(f"  ✓ {spec['username']:<12} ({spec['real_name']}) [{spec['role_code']}]")

    await db.commit()
    print()
    return user_ids


async def _seed_experiments(db: AsyncSession, teacher_id: int) -> None:
    """插入种子实验数据，已存在的跳过。"""
    print("=" * 50)
    print("  示例实验数据")
    print("=" * 50)
    now = datetime.utcnow()

    for spec in SEED_EXPERIMENTS:
        result = await db.execute(
            select(Experiment).where(Experiment.code == spec["code"])
        )
        if result.scalar_one_or_none():
            print(f"  - 实验「{spec['name']}」已存在，跳过")
            continue

        exp = Experiment(
            name=spec["name"],
            code=spec["code"],
            description=spec["description"],
            status=ExperimentStatus.ACTIVE,
            created_by=teacher_id,
        )
        db.add(exp)
        await db.flush()

        for v_spec in spec["versions"]:
            is_published = v_spec["publish_status"] == PublishStatus.PUBLISHED
            # 10-S1-1: 移除 is_visible 字段（可见性由 publish_status + Experiment.status 决定）
            version = ExperimentVersion(
                experiment_id=exp.id,
                version_name=v_spec["version_name"],
                environment_key=v_spec["environment_key"],
                image_name=v_spec["image_name"],
                launch_args_template=v_spec["launch_args_template"],
                publish_status=v_spec["publish_status"],
                published_at=now if is_published else None,
            )
            db.add(version)
            await db.flush()

            if is_published and v_spec["publish_note"]:
                log = ExperimentPublishLog(
                    experiment_id=exp.id,
                    version_id=version.id,
                    operator_id=teacher_id,
                    publish_note=v_spec["publish_note"],
                )
                db.add(log)

            status_label = "已发布" if is_published else "草稿"
            print(f"  ✓ 实验「{exp.name}」版本 {version.version_name} [{status_label}]")

    await db.commit()
    print()


async def init_database() -> None:
    await _create_tables()

    async with AsyncSessionLocal() as db:
        user_ids = await _seed_users(db)
        teacher_id = user_ids.get("teacher")
        if teacher_id:
            await _seed_experiments(db, teacher_id)
        else:
            print("  ⚠ 未找到 teacher 账号，跳过实验种子数据\n")

    print("=" * 50)
    print("  初始化完成")
    print(f"  数据库文件: edubot.db")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(init_database())
