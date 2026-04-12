"""
考试域 CRUD + API 端点测试（Sprint 11）

覆盖：
1. 考试定义 CRUD（创建/列表/更新/删除/重复编码）
2. 考试生命周期状态机（publish / archive / republish）
3. 冻结字段写保护
4. 乐观锁并发冲突
5. 环境快照 CRUD（创建/列表/更新/删除/引用保护）
6. 文件快照 CRUD
7. 测评脚本 CRUD + validate_status 自动校验
8. 端点层集成测试（直接调用 endpoint handler）
"""

import pytest
from datetime import datetime, timedelta

from app.crud import exam as crud_exam
from app.crud import exam_env_snapshot as crud_env_snap
from app.crud import exam_file_snapshot as crud_file_snap
from app.crud import exam_eval_script as crud_eval_script
from app.api.v1.endpoints.teacher.exams import (
    create_exam as create_exam_endpoint,
    get_exam as get_exam_endpoint,
    list_exams as list_exams_endpoint,
    update_exam as update_exam_endpoint,
    delete_exam as delete_exam_endpoint,
    publish_exam as publish_exam_endpoint,
    archive_exam as archive_exam_endpoint,
    republish_exam as republish_exam_endpoint,
)
from app.schemas.exam import ExamCreateRequest, ExamUpdateRequest


TEACHER_ID = 1


# ═══════════════════════════════════════════════════════════════════════════════
#  辅助函数
# ═══════════════════════════════════════════════════════════════════════════════


async def _create_exam(db, code_suffix="", **overrides):
    """快捷创建考试"""
    defaults = dict(
        name=f"测试考试_{code_suffix}",
        code=f"test_{code_suffix}" if code_suffix else f"test_{id(db)}",
        exam_mode="result_run",
        description="单元测试",
        created_by=TEACHER_ID,
    )
    defaults.update(overrides)
    return await crud_exam.create_exam(db, **defaults)


async def _create_env_snapshot(db, name_suffix=""):
    return await crud_env_snap.create_env_snapshot(
        db,
        name=f"env_snap_{name_suffix or id(db)}",
        container_target_dir="/home/ubuntu20/catkin_ws",
        created_by=TEACHER_ID,
    )


async def _create_file_snapshot(db, name_suffix=""):
    return await crud_file_snap.create_file_snapshot(
        db,
        name=f"file_snap_{name_suffix or id(db)}",
        created_by=TEACHER_ID,
    )


async def _create_eval_script(db, name_suffix="", entry_point="evaluate.sh"):
    return await crud_eval_script.create_eval_script(
        db,
        name=f"script_{name_suffix or id(db)}",
        entry_point=entry_point,
        description="测试脚本",
        created_by=TEACHER_ID,
    )


async def _make_published_exam(db, code_suffix):
    """创建一个已发布的考试（附带全部资源关联）"""
    exam = await _create_exam(db, code_suffix=code_suffix)
    env = await _create_env_snapshot(db, name_suffix=code_suffix)
    fsnap = await _create_file_snapshot(db, name_suffix=code_suffix)
    script = await _create_eval_script(db, name_suffix=code_suffix)

    await crud_exam.update_exam(db, exam=exam, update_data={
        "env_snapshot_id": env.id,
        "file_snapshot_id": fsnap.id,
        "eval_script_id": script.id,
    })
    exam = await crud_exam.publish_exam(db, exam=exam)
    return exam, env, fsnap, script


# ═══════════════════════════════════════════════════════════════════════════════
#  1. 考试定义 CRUD
# ═══════════════════════════════════════════════════════════════════════════════


class TestExamCRUD:

    @pytest.mark.asyncio
    async def test_create_exam(self, db_session):
        exam = await _create_exam(db_session, code_suffix="create_01")
        assert exam.id is not None
        assert exam.name == "测试考试_create_01"
        assert exam.code == "test_create_01"
        assert exam.status.value == "draft"
        assert exam.exam_mode.value == "result_run"

    @pytest.mark.asyncio
    async def test_create_exam_duplicate_code(self, db_session):
        await _create_exam(db_session, code_suffix="dup_01")
        with pytest.raises(ValueError, match="EXAM_CODE_DUPLICATED"):
            await _create_exam(db_session, code_suffix="dup_01")

    @pytest.mark.asyncio
    async def test_get_exam(self, db_session):
        exam = await _create_exam(db_session, code_suffix="get_01")
        fetched = await crud_exam.get_exam(db_session, exam.id)
        assert fetched is not None
        assert fetched.id == exam.id
        assert fetched.code == "test_get_01"

    @pytest.mark.asyncio
    async def test_get_exam_not_found(self, db_session):
        fetched = await crud_exam.get_exam(db_session, 99999)
        assert fetched is None

    @pytest.mark.asyncio
    async def test_list_exams(self, db_session):
        await _create_exam(db_session, code_suffix="list_01")
        await _create_exam(db_session, code_suffix="list_02")

        exams, total = await crud_exam.list_exams(
            db_session, created_by=TEACHER_ID, page=1, page_size=10
        )
        assert total >= 2
        assert len(exams) >= 2

    @pytest.mark.asyncio
    async def test_list_exams_with_keyword(self, db_session):
        await _create_exam(db_session, code_suffix="kw_alpha", name="导航考试")
        await _create_exam(db_session, code_suffix="kw_beta", name="SLAM考试")

        exams, total = await crud_exam.list_exams(
            db_session, created_by=TEACHER_ID, keyword="导航"
        )
        assert total == 1
        assert exams[0].name == "导航考试"

    @pytest.mark.asyncio
    async def test_list_exams_with_status_filter(self, db_session):
        await _create_exam(db_session, code_suffix="sf_01")
        exams, total = await crud_exam.list_exams(
            db_session, created_by=TEACHER_ID, status="draft"
        )
        assert total >= 1

        exams2, total2 = await crud_exam.list_exams(
            db_session, created_by=TEACHER_ID, status="published"
        )
        assert total2 == 0

    @pytest.mark.asyncio
    async def test_update_exam(self, db_session):
        exam = await _create_exam(db_session, code_suffix="upd_01")
        exam = await crud_exam.update_exam(
            db_session, exam=exam, update_data={"name": "改名考试", "description": "新描述"}
        )
        assert exam.name == "改名考试"
        assert exam.description == "新描述"

    @pytest.mark.asyncio
    async def test_update_exam_mode(self, db_session):
        exam = await _create_exam(db_session, code_suffix="upd_mode")
        exam = await crud_exam.update_exam(
            db_session, exam=exam, update_data={"exam_mode": "process_run"}
        )
        assert exam.exam_mode.value == "process_run"

    @pytest.mark.asyncio
    async def test_delete_exam_requires_archived(self, db_session):
        exam = await _create_exam(db_session, code_suffix="del_01")
        with pytest.raises(ValueError, match="EXAM_DELETE_REQUIRES_ARCHIVED"):
            await crud_exam.delete_exam(db_session, exam=exam)

    @pytest.mark.asyncio
    async def test_delete_exam_archived_ok(self, db_session):
        exam, env, fsnap, script = await _make_published_exam(db_session, "del_ok")
        exam = await crud_exam.archive_exam(db_session, exam=exam)
        assert exam.status.value == "archived"
        await crud_exam.delete_exam(db_session, exam=exam)
        assert await crud_exam.get_exam(db_session, exam.id) is None


# ═══════════════════════════════════════════════════════════════════════════════
#  2. 考试状态机
# ═══════════════════════════════════════════════════════════════════════════════


class TestExamStateMachine:

    @pytest.mark.asyncio
    async def test_full_lifecycle(self, db_session):
        """draft → published → archived → republished(published)"""
        exam, _, _, _ = await _make_published_exam(db_session, "lifecycle")

        assert exam.status.value == "published"
        assert exam.published_at is not None

        # archive
        exam = await crud_exam.archive_exam(db_session, exam=exam)
        assert exam.status.value == "archived"

        # republish
        exam = await crud_exam.republish_exam(db_session, exam=exam)
        assert exam.status.value == "published"

    @pytest.mark.asyncio
    async def test_publish_requires_draft(self, db_session):
        exam, _, _, _ = await _make_published_exam(db_session, "pub_dup")
        with pytest.raises(ValueError, match="EXAM_NOT_DRAFT"):
            await crud_exam.publish_exam(db_session, exam=exam)

    @pytest.mark.asyncio
    async def test_publish_requires_resources(self, db_session):
        exam = await _create_exam(db_session, code_suffix="pub_inc")
        with pytest.raises(ValueError, match="EXAM_PUBLISH_INCOMPLETE"):
            await crud_exam.publish_exam(db_session, exam=exam)

    @pytest.mark.asyncio
    async def test_archive_requires_published(self, db_session):
        exam = await _create_exam(db_session, code_suffix="arch_bad")
        with pytest.raises(ValueError, match="EXAM_NOT_PUBLISHED"):
            await crud_exam.archive_exam(db_session, exam=exam)

    @pytest.mark.asyncio
    async def test_republish_requires_archived(self, db_session):
        exam, _, _, _ = await _make_published_exam(db_session, "repub_bad")
        with pytest.raises(ValueError, match="EXAM_NOT_ARCHIVED"):
            await crud_exam.republish_exam(db_session, exam=exam)

    @pytest.mark.asyncio
    async def test_frozen_fields_on_published(self, db_session):
        """已发布考试的冻结字段不可修改"""
        exam, _, _, _ = await _make_published_exam(db_session, "frozen")

        for field in ["exam_mode", "env_snapshot_id", "file_snapshot_id",
                       "eval_script_id", "sidecar_policy"]:
            with pytest.raises(ValueError, match="EXAM_FIELD_FROZEN"):
                value = "process_run" if field == "exam_mode" else 999
                if field == "sidecar_policy":
                    value = {"a": 1}
                await crud_exam.update_exam(
                    db_session, exam=exam, update_data={field: value}
                )

    @pytest.mark.asyncio
    async def test_non_frozen_fields_on_published(self, db_session):
        """已发布考试的非冻结字段仍可修改"""
        exam, _, _, _ = await _make_published_exam(db_session, "nonfrozen")

        exam = await crud_exam.update_exam(
            db_session, exam=exam, update_data={
                "name": "发布后改名",
                "description": "发布后改描述",
                "runtime_policy": {"timeout": 300},
            }
        )
        assert exam.name == "发布后改名"
        assert exam.description == "发布后改描述"
        assert exam.runtime_policy_json == {"timeout": 300}

    @pytest.mark.asyncio
    async def test_optimistic_lock_conflict(self, db_session):
        """乐观锁：客户端持有过期的 updated_at"""
        exam = await _create_exam(db_session, code_suffix="optlock")
        stale_ts = (exam.updated_at - timedelta(hours=1)).isoformat()

        with pytest.raises(ValueError, match="EXAM_CONCURRENT_MODIFIED"):
            await crud_exam.update_exam(
                db_session, exam=exam, update_data={
                    "name": "并发写入",
                    "updated_at": stale_ts,
                }
            )

    @pytest.mark.asyncio
    async def test_optimistic_lock_pass(self, db_session):
        """乐观锁：客户端持有最新的 updated_at"""
        exam = await _create_exam(db_session, code_suffix="optok")
        fresh_ts = exam.updated_at.isoformat()

        exam = await crud_exam.update_exam(
            db_session, exam=exam, update_data={
                "name": "正常更新",
                "updated_at": fresh_ts,
            }
        )
        assert exam.name == "正常更新"


# ═══════════════════════════════════════════════════════════════════════════════
#  3. 环境快照 CRUD
# ═══════════════════════════════════════════════════════════════════════════════


class TestEnvSnapshotCRUD:

    @pytest.mark.asyncio
    async def test_create_env_snapshot(self, db_session):
        snap = await _create_env_snapshot(db_session, name_suffix="create")
        assert snap.id is not None
        assert snap.file_count == 0
        assert snap.total_size_bytes == 0
        assert snap.container_target_dir == "/home/ubuntu20/catkin_ws"
        assert snap.storage_root != ""

    @pytest.mark.asyncio
    async def test_list_env_snapshots(self, db_session):
        await _create_env_snapshot(db_session, name_suffix="list1")
        await _create_env_snapshot(db_session, name_suffix="list2")

        snaps, total = await crud_env_snap.list_env_snapshots(
            db_session, created_by=TEACHER_ID
        )
        assert total >= 2

    @pytest.mark.asyncio
    async def test_update_env_snapshot(self, db_session):
        snap = await _create_env_snapshot(db_session, name_suffix="upd")
        snap = await crud_env_snap.update_env_snapshot(
            db_session, snapshot=snap, name="更名快照"
        )
        assert snap.name == "更名快照"

    @pytest.mark.asyncio
    async def test_delete_env_snapshot(self, db_session):
        snap = await _create_env_snapshot(db_session, name_suffix="del")
        await crud_env_snap.delete_env_snapshot(db_session, snapshot=snap)
        assert await crud_env_snap.get_env_snapshot(db_session, snap.id) is None

    @pytest.mark.asyncio
    async def test_delete_env_snapshot_in_use(self, db_session):
        """被考试引用的环境快照不可删除"""
        exam, env, _, _ = await _make_published_exam(db_session, "envref")
        with pytest.raises(ValueError, match="SNAPSHOT_IN_USE"):
            await crud_env_snap.delete_env_snapshot(db_session, snapshot=env)

    @pytest.mark.asyncio
    async def test_update_stats(self, db_session):
        snap = await _create_env_snapshot(db_session, name_suffix="stats")
        snap = await crud_env_snap.update_env_snapshot_stats(
            db_session, snapshot=snap, file_count=5, total_size_bytes=1024
        )
        assert snap.file_count == 5
        assert snap.total_size_bytes == 1024


# ═══════════════════════════════════════════════════════════════════════════════
#  4. 文件快照 CRUD
# ═══════════════════════════════════════════════════════════════════════════════


class TestFileSnapshotCRUD:

    @pytest.mark.asyncio
    async def test_create_file_snapshot(self, db_session):
        snap = await _create_file_snapshot(db_session, name_suffix="create")
        assert snap.id is not None
        assert snap.file_count == 0
        assert snap.storage_root != ""

    @pytest.mark.asyncio
    async def test_list_file_snapshots(self, db_session):
        await _create_file_snapshot(db_session, name_suffix="flist1")
        await _create_file_snapshot(db_session, name_suffix="flist2")

        snaps, total = await crud_file_snap.list_file_snapshots(
            db_session, created_by=TEACHER_ID
        )
        assert total >= 2

    @pytest.mark.asyncio
    async def test_delete_file_snapshot(self, db_session):
        snap = await _create_file_snapshot(db_session, name_suffix="fdel")
        await crud_file_snap.delete_file_snapshot(db_session, snapshot=snap)
        assert await crud_file_snap.get_file_snapshot(db_session, snap.id) is None

    @pytest.mark.asyncio
    async def test_delete_file_snapshot_in_use(self, db_session):
        """被考试引用的文件快照不可删除"""
        exam, _, fsnap, _ = await _make_published_exam(db_session, "fileref")
        with pytest.raises(ValueError, match="SNAPSHOT_IN_USE"):
            await crud_file_snap.delete_file_snapshot(db_session, snapshot=fsnap)


# ═══════════════════════════════════════════════════════════════════════════════
#  5. 测评脚本 CRUD
# ═══════════════════════════════════════════════════════════════════════════════


class TestEvalScriptCRUD:

    @pytest.mark.asyncio
    async def test_create_eval_script(self, db_session):
        script = await _create_eval_script(db_session, name_suffix="create")
        assert script.id is not None
        assert script.entry_point == "evaluate.sh"
        assert script.validate_status.value == "pending"
        assert script.storage_root != ""

    @pytest.mark.asyncio
    async def test_list_eval_scripts(self, db_session):
        await _create_eval_script(db_session, name_suffix="slist1")
        await _create_eval_script(db_session, name_suffix="slist2")

        scripts, total = await crud_eval_script.list_eval_scripts(
            db_session, created_by=TEACHER_ID
        )
        assert total >= 2

    @pytest.mark.asyncio
    async def test_update_eval_script(self, db_session):
        script = await _create_eval_script(db_session, name_suffix="supd")
        script = await crud_eval_script.update_eval_script(
            db_session, script=script, name="改名脚本", entry_point="run.sh"
        )
        assert script.name == "改名脚本"
        assert script.entry_point == "run.sh"

    @pytest.mark.asyncio
    async def test_delete_eval_script(self, db_session):
        script = await _create_eval_script(db_session, name_suffix="sdel")
        await crud_eval_script.delete_eval_script(db_session, script=script)
        assert await crud_eval_script.get_eval_script(db_session, script.id) is None

    @pytest.mark.asyncio
    async def test_delete_eval_script_in_use(self, db_session):
        """被考试引用的脚本不可删除"""
        exam, _, _, script = await _make_published_exam(db_session, "scriptref")
        with pytest.raises(ValueError, match="SNAPSHOT_IN_USE"):
            await crud_eval_script.delete_eval_script(db_session, script=script)


# ═══════════════════════════════════════════════════════════════════════════════
#  6. 端点层集成测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestExamEndpoints:
    """直接调用 endpoint handler（绕过 HTTP 传输层）"""

    @pytest.mark.asyncio
    async def test_create_exam_endpoint(self, db_session):
        res = await create_exam_endpoint(
            data=ExamCreateRequest(
                name="端点测试考试",
                code="ep_create_01",
                exam_mode="result_run",
                description="端点层测试",
            ),
            db=db_session,
            teacher_id=TEACHER_ID,
        )
        assert res.code == 0
        assert res.data is not None
        assert res.data.name == "端点测试考试"
        assert res.data.status == "draft"

    @pytest.mark.asyncio
    async def test_get_exam_endpoint(self, db_session):
        exam = await _create_exam(db_session, code_suffix="ep_get")
        res = await get_exam_endpoint(
            exam_id=exam.id, db=db_session, teacher_id=TEACHER_ID
        )
        assert res.code == 0
        assert res.data.id == exam.id

    @pytest.mark.asyncio
    async def test_list_exams_endpoint(self, db_session):
        await _create_exam(db_session, code_suffix="ep_list_1")
        await _create_exam(db_session, code_suffix="ep_list_2")
        res = await list_exams_endpoint(
            page=1, page_size=10, keyword=None,
            exam_status=None, exam_mode=None,
            db=db_session, teacher_id=TEACHER_ID,
        )
        assert res.code == 0
        assert res.data.total >= 2

    @pytest.mark.asyncio
    async def test_update_exam_endpoint(self, db_session):
        exam = await _create_exam(db_session, code_suffix="ep_upd")
        res = await update_exam_endpoint(
            exam_id=exam.id,
            data=ExamUpdateRequest(name="端点改名", description="新描述"),
            db=db_session,
            teacher_id=TEACHER_ID,
        )
        assert res.code == 0
        assert res.data.name == "端点改名"

    @pytest.mark.asyncio
    async def test_publish_archive_republish_endpoint(self, db_session):
        """端点层生命周期：publish → archive → republish"""
        exam, env, fsnap, script = await _make_published_exam(db_session, "ep_lc")

        # 已经 published，验证
        res = await get_exam_endpoint(
            exam_id=exam.id, db=db_session, teacher_id=TEACHER_ID
        )
        assert res.data.status == "published"

        # archive
        res = await archive_exam_endpoint(
            exam_id=exam.id, db=db_session, teacher_id=TEACHER_ID
        )
        assert res.code == 0
        assert res.data.status == "archived"

        # republish
        res = await republish_exam_endpoint(
            exam_id=exam.id, db=db_session, teacher_id=TEACHER_ID
        )
        assert res.code == 0
        assert res.data.status == "published"

    @pytest.mark.asyncio
    async def test_delete_exam_endpoint_requires_archived(self, db_session):
        """端点层删除：必须归档后才能删"""
        from fastapi import HTTPException

        exam = await _create_exam(db_session, code_suffix="ep_del")
        with pytest.raises(HTTPException) as exc_info:
            await delete_exam_endpoint(
                exam_id=exam.id, db=db_session, teacher_id=TEACHER_ID
            )
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_frozen_field_endpoint(self, db_session):
        """端点层冻结字段测试"""
        from fastapi import HTTPException

        exam, _, _, _ = await _make_published_exam(db_session, "ep_frozen")
        with pytest.raises(HTTPException) as exc_info:
            await update_exam_endpoint(
                exam_id=exam.id,
                data=ExamUpdateRequest(exam_mode="process_run"),
                db=db_session,
                teacher_id=TEACHER_ID,
            )
        assert exc_info.value.status_code == 409
        assert "FROZEN" in exc_info.value.detail
