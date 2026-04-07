import json
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

from app.crud import experiment as experiment_crud
from app.crud import simulation_task as simulation_task_crud
from app.models.container import ContainerStatus, SimContainer
from app.models.experiment import PublishStatus
from app.models.simulation_task import SimulationTaskStatus
from app.api.v1.endpoints.student.tasks import get_task as get_task_endpoint
from app.schemas.experiment import ExperimentVersionUpdate, StudentSimulationStartRequest
from app.api.v1.endpoints.student.simulation import start_simulation
from app.api.v1.endpoints.teacher.experiments import update_version as update_version_endpoint


@pytest.mark.asyncio
async def test_create_and_query_experiment_version_and_publish_log(db_session):
    exp = await experiment_crud.create_experiment(
        db_session,
        name="导航实验",
        code="nav_exp",
        description="第10期测试实验",
        created_by=1,
    )

    assert exp.id is not None
    assert exp.code == "nav_exp"

    version = await experiment_crud.create_version(
        db_session,
        experiment_id=exp.id,
        version_name="v1.0.0",
        environment_key="ros-noetic-nav",
        image_name="gzweb_sim:v1",
        launch_file_path="/launch/nav.launch",
        launch_args_template={"use_sim_time": "true"},
        startup_script_ref=None,
        file_bundle_id=None,
        is_visible=True,
    )

    assert version.experiment_id == exp.id
    assert version.publish_status == PublishStatus.DRAFT

    log = await experiment_crud.publish_version(
        db_session,
        experiment_id=exp.id,
        version=version,
        operator_id=1,
        note="首次发布",
    )

    assert log.id is not None

    reloaded_version = await experiment_crud.get_version(db_session, version.id)
    assert reloaded_version is not None
    assert reloaded_version.publish_status == PublishStatus.PUBLISHED

    available_versions = await experiment_crud.list_student_available_versions(db_session)
    assert any(item.id == version.id for item in available_versions)


@pytest.mark.asyncio
async def test_start_simulation_reuse_running_container_when_same_version(db_session, test_student, monkeypatch):
    exp = await experiment_crud.create_experiment(
        db_session,
        name="跟踪实验",
        code="track_exp",
        description="复用容器测试",
        created_by=1,
    )

    version = await experiment_crud.create_version(
        db_session,
        experiment_id=exp.id,
        version_name="v2.0.0",
        environment_key="ros-noetic-track",
        image_name="gzweb_sim:v2",
        launch_file_path="/launch/track.launch",
        launch_args_template={},
        startup_script_ref=None,
        file_bundle_id=None,
        is_visible=True,
    )

    await experiment_crud.publish_version(
        db_session,
        experiment_id=exp.id,
        version=version,
        operator_id=1,
        note=None,
    )

    class ExistingContainer:
        current_version_id = version.id

        class _Status:
            value = "running"

        status = _Status()

    import app.api.v1.endpoints.student.simulation as simulation_module

    async def fake_get_container_by_user(*args, **kwargs):
        return ExistingContainer()

    monkeypatch.setattr(simulation_module.crud_container, "get_container_by_user", fake_get_container_by_user)

    res = await start_simulation(
        StudentSimulationStartRequest(version_id=version.id, force_recreate=False),
        db=db_session,
        student_id=test_student.id,
    )

    assert res.code == 0
    assert res.data is not None
    assert res.data.container_status == "running"
    assert res.data.experiment_context["version_id"] == version.id


@pytest.mark.asyncio
async def test_start_simulation_recreate_container_with_new_version(db_session, test_student, monkeypatch):
    exp = await experiment_crud.create_experiment(
        db_session,
        name="重建实验",
        code="recreate_exp",
        description="重建容器测试",
        created_by=1,
    )

    version = await experiment_crud.create_version(
        db_session,
        experiment_id=exp.id,
        version_name="v3.0.0",
        environment_key="ros-noetic-recreate",
        image_name="gzweb_sim:v3",
        launch_file_path="/launch/recreate.launch",
        launch_args_template={},
        startup_script_ref=None,
        file_bundle_id=None,
        is_visible=True,
    )

    await experiment_crud.publish_version(
        db_session,
        experiment_id=exp.id,
        version=version,
        operator_id=1,
        note="发布v3",
    )

    class OldContainer:
        current_version_id = None

        class _Status:
            value = "stopped"

        status = _Status()

    import app.api.v1.endpoints.student.simulation as simulation_module

    async def fake_get_container_by_user(*args, **kwargs):
        return OldContainer()

    async def fake_delete_container(*args, **kwargs):
        return True

    async def fake_create_container(*args, **kwargs):
        new_container = SimContainer(
            user_id=test_student.id,
            image_name=version.image_name,
            status=ContainerStatus.RUNNING,
            gzbridge_port=38080,
            rosbridge_port=39090,
            container_id="fake_new_container",
        )
        setattr(new_container, "current_version_id", version.id)
        return new_container

    monkeypatch.setattr(simulation_module.crud_container, "get_container_by_user", fake_get_container_by_user)
    monkeypatch.setattr(simulation_module.crud_container, "delete_container", fake_delete_container)
    monkeypatch.setattr(simulation_module.crud_container, "create_container", fake_create_container)

    def fake_create_task(coro):
        coro.close()

        class _DummyTask:
            pass

        return _DummyTask()

    monkeypatch.setattr(simulation_module.asyncio, "create_task", fake_create_task)

    res = await start_simulation(
        StudentSimulationStartRequest(version_id=version.id, force_recreate=False),
        db=db_session,
        student_id=test_student.id,
    )

    assert res.status_code == 202
    payload = json.loads(res.body.decode("utf-8"))
    assert payload["code"] == 0
    assert payload["data"]["container_status"] == "creating"
    assert payload["data"]["task_id"] is not None
    assert payload["data"]["experiment_context"]["environment_key"] == "ros-noetic-recreate"
    assert payload["data"]["experiment_context"]["version_id"] == version.id


@pytest.mark.asyncio
async def test_query_simulation_task_by_owner(db_session, test_student):
    task = await simulation_task_crud.create_task(
        db_session,
        student_id=test_student.id,
        target_version_id=123,
        container_id=None,
    )

    res = await get_task_endpoint(
        task_id=task.task_id,
        db=db_session,
        student_id=test_student.id,
    )

    assert res.code == 0
    assert res.data is not None
    assert res.data.task_id == task.task_id
    assert res.data.task_status in ("PENDING", "IN_PROGRESS", "SUCCEEDED", "FAILED")


@pytest.mark.asyncio
async def test_update_experiment_version_only_allows_draft(db_session):
    exp = await experiment_crud.create_experiment(
        db_session,
        name="草稿可编辑实验",
        code="editable_draft_exp",
        description="更新版本测试",
        created_by=1,
    )

    version = await experiment_crud.create_version(
        db_session,
        experiment_id=exp.id,
        version_name="v1.0.0",
        environment_key="ros-noetic-draft",
        image_name="gzweb_sim:v1",
        launch_file_path="/launch/draft.launch",
        launch_args_template={"use_sim_time": "false"},
        startup_script_ref="boot_v1",
        file_bundle_id=None,
        is_visible=True,
    )

    res = await update_version_endpoint(
        experiment_id=exp.id,
        version_id=version.id,
        data=ExperimentVersionUpdate(
            version_name="v1.0.1",
            environment_key="ros-noetic-draft-updated",
            image_name="gzweb_sim:v1.1",
            launch_file_path="/launch/draft_v2.launch",
            launch_args_template={"use_sim_time": "true"},
            startup_script_ref="boot_v2",
            file_bundle_id=123,
            is_visible=False,
        ),
        db=db_session,
        _=1,
    )

    assert res.code == 0
    assert res.data is not None
    assert res.data.version_name == "v1.0.1"
    assert res.data.environment_key == "ros-noetic-draft-updated"
    assert res.data.publish_status == "draft"


@pytest.mark.asyncio
async def test_update_experiment_version_rejects_published(db_session):
    exp = await experiment_crud.create_experiment(
        db_session,
        name="已发布只读实验",
        code="readonly_published_exp",
        description="发布后不可编辑测试",
        created_by=1,
    )

    version = await experiment_crud.create_version(
        db_session,
        experiment_id=exp.id,
        version_name="v2.0.0",
        environment_key="ros-noetic-published",
        image_name="gzweb_sim:v2",
        launch_file_path="/launch/published.launch",
        launch_args_template={"mode": "stable"},
        startup_script_ref=None,
        file_bundle_id=None,
        is_visible=True,
    )

    await experiment_crud.publish_version(
        db_session,
        experiment_id=exp.id,
        version=version,
        operator_id=1,
        note="发布后应只读",
    )

    with pytest.raises(HTTPException) as exc_info:
        await update_version_endpoint(
            experiment_id=exp.id,
            version_id=version.id,
            data=ExperimentVersionUpdate(
                version_name="v2.0.1",
                environment_key="ros-noetic-published-updated",
                image_name="gzweb_sim:v2.1",
                launch_file_path="/launch/published_v2.launch",
                launch_args_template={"mode": "edited"},
                startup_script_ref="forbidden_edit",
                file_bundle_id=None,
                is_visible=True,
            ),
            db=db_session,
            _=1,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "仅草稿版本允许编辑"


# ── Nil Path ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_available_versions_empty_when_no_published(db_session):
    """Nil Path：数据库中无已发布版本时，可用列表应为空。"""
    versions = await experiment_crud.list_student_available_versions(db_session)
    assert versions == []


# ── Error Path ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_start_simulation_version_not_found(db_session, test_student):
    """Error Path：传入不存在的 version_id 时，应返回 404。"""
    with pytest.raises(HTTPException) as exc_info:
        await start_simulation(
            StudentSimulationStartRequest(version_id=99999, force_recreate=False),
            db=db_session,
            student_id=test_student.id,
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "EXPERIMENT_VERSION_NOT_FOUND"


@pytest.mark.asyncio
async def test_start_simulation_draft_version_not_accessible(db_session, test_student):
    """Error Path：草稿版本（未发布）对学生不可见，应返回 404。"""
    exp = await experiment_crud.create_experiment(
        db_session,
        name="草稿实验",
        code="draft_only_exp",
        description="草稿不可见测试",
        created_by=1,
    )
    version = await experiment_crud.create_version(
        db_session,
        experiment_id=exp.id,
        version_name="v1.0.0",
        environment_key="ros-draft",
        image_name="gzweb_sim:v1",
        launch_file_path="/launch/nav.launch",
        launch_args_template={},
        startup_script_ref=None,
        file_bundle_id=None,
        is_visible=True,
    )
    # 故意不调用 publish_version，保持 draft 状态

    with pytest.raises(HTTPException) as exc_info:
        await start_simulation(
            StudentSimulationStartRequest(version_id=version.id, force_recreate=False),
            db=db_session,
            student_id=test_student.id,
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "EXPERIMENT_VERSION_NOT_FOUND"


# ── 并发冲突 ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_start_simulation_concurrent_conflict_returns_409(db_session, test_student, monkeypatch):
    """并发冲突：同一学生已有进行中任务时，第二次请求应返回 409。"""
    exp = await experiment_crud.create_experiment(
        db_session,
        name="并发实验",
        code="concurrent_exp",
        description="并发冲突测试",
        created_by=1,
    )
    version = await experiment_crud.create_version(
        db_session,
        experiment_id=exp.id,
        version_name="v1.0.0",
        environment_key="ros-concurrent",
        image_name="gzweb_sim:v1",
        launch_file_path="/launch/nav.launch",
        launch_args_template={},
        startup_script_ref=None,
        file_bundle_id=None,
        is_visible=True,
    )
    await experiment_crud.publish_version(
        db_session, experiment_id=exp.id, version=version, operator_id=1, note=None
    )

    # 预先创建一个进行中任务，模拟并发场景
    active_task = await simulation_task_crud.create_task(
        db_session, student_id=test_student.id, target_version_id=version.id, container_id=None
    )
    await simulation_task_crud.mark_task_running(db_session, task=active_task)

    import app.api.v1.endpoints.student.simulation as simulation_module

    async def fake_get_container_by_user(*args, **kwargs):
        return None

    monkeypatch.setattr(simulation_module.crud_container, "get_container_by_user", fake_get_container_by_user)

    with pytest.raises(HTTPException) as exc_info:
        await start_simulation(
            StudentSimulationStartRequest(version_id=version.id, force_recreate=False),
            db=db_session,
            student_id=test_student.id,
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "CONTAINER_REBUILD_IN_PROGRESS"


# ── 鉴权/越权 ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_query_task_forbidden_for_other_student(db_session, test_student):
    """鉴权：学生查询他人任务时应返回 403。"""
    task = await simulation_task_crud.create_task(
        db_session,
        student_id=test_student.id,
        target_version_id=1,
        container_id=None,
    )
    other_student_id = test_student.id + 999

    with pytest.raises(HTTPException) as exc_info:
        await get_task_endpoint(
            task_id=task.task_id,
            db=db_session,
            student_id=other_student_id,
        )
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "FORBIDDEN"


@pytest.mark.asyncio
async def test_query_task_not_found_returns_404(db_session, test_student):
    """鉴权：查询不存在的 task_id 应返回 404。"""
    with pytest.raises(HTTPException) as exc_info:
        await get_task_endpoint(
            task_id="00000000-0000-0000-0000-000000000000",
            db=db_session,
            student_id=test_student.id,
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "TASK_NOT_FOUND"


# ── 孤儿任务回收 ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_orphan_task_recovery(db_session, test_student):
    """服务恢复：updated_at 超过阈值的 PENDING/IN_PROGRESS 任务应被标记为 FAILED+retryable。"""
    # 创建两个孤儿任务（手动设置 updated_at 为 10 分钟前）
    stale_time = datetime.utcnow() - timedelta(minutes=10)

    task_pending = await simulation_task_crud.create_task(
        db_session, student_id=test_student.id, target_version_id=1, container_id=None
    )
    task_pending.updated_at = stale_time
    await db_session.commit()

    task_running = await simulation_task_crud.create_task(
        db_session, student_id=test_student.id, target_version_id=2, container_id=None
    )
    await simulation_task_crud.mark_task_running(db_session, task=task_running)
    task_running.updated_at = stale_time
    await db_session.commit()

    # 创建一个新鲜的 PENDING 任务，不应被回收
    fresh_task = await simulation_task_crud.create_task(
        db_session, student_id=test_student.id, target_version_id=3, container_id=None
    )

    recovered = await simulation_task_crud.recover_orphan_tasks(db_session, stale_minutes=5)
    assert recovered == 2

    await db_session.refresh(task_pending)
    await db_session.refresh(task_running)
    await db_session.refresh(fresh_task)

    assert task_pending.status == SimulationTaskStatus.FAILED
    assert task_pending.retryable is True
    assert task_pending.error_code == "ORPHAN_TASK_RECOVERED"

    assert task_running.status == SimulationTaskStatus.FAILED
    assert task_running.retryable is True

    # 新鲜任务不受影响
    assert fresh_task.status == SimulationTaskStatus.PENDING


# ══════════════════════════════════════════════════════════════════════════════
# 文件分发相关测试（SDD §11.1 分发任务化 / 全选 / 白名单 / 权限修复 / 分发失败）
# ══════════════════════════════════════════════════════════════════════════════

# ── 公共辅助 ──────────────────────────────────────────────────────────────────

SAMPLE_MANIFEST = [
    {"relative_path": "maps/map.yaml", "chmod_mode": "0644"},
    {"relative_path": "maps/map.pgm",  "chmod_mode": "0644"},
    {"relative_path": "launch/nav.launch", "chmod_mode": "0755"},
]


async def _setup_published_version_with_bundle(db_session, exp_code: str):
    """辅助：创建已发布版本 + 有效文件包，返回 (version, bundle)。"""
    from app.crud import experiment as experiment_crud

    exp = await experiment_crud.create_experiment(
        db_session,
        name=f"分发测试实验-{exp_code}",
        code=exp_code,
        description=None,
        created_by=1,
    )
    bundle = await experiment_crud.create_bundle(
        db_session,
        experiment_id=exp.id,
        file_manifest=SAMPLE_MANIFEST,
        created_by=1,
    )
    version = await experiment_crud.create_version(
        db_session,
        experiment_id=exp.id,
        version_name="v1.0.0",
        environment_key="ros-distribute",
        image_name="gzweb_sim:v1",
        launch_file_path="/launch/nav.launch",
        launch_args_template={},
        startup_script_ref=None,
        file_bundle_id=bundle.id,
        is_visible=True,
    )
    await experiment_crud.publish_version(
        db_session, experiment_id=exp.id, version=version, operator_id=1, note=None
    )
    return version, bundle


# ── 8. 分发任务化 ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_distribute_creates_task_returns_202(db_session, test_student, monkeypatch):
    """分发任务化：POST /files/distribute 应返回 202 + task_id，并在 DB 中创建任务。"""
    import json
    import app.api.v1.endpoints.student.simulation as simulation_module
    from app.api.v1.endpoints.student.simulation import distribute_files
    from app.schemas.experiment import FileDistributeRequest

    version, _ = await _setup_published_version_with_bundle(db_session, "dist_task_exp")

    def fake_create_task(coro):
        coro.close()

        class _Dummy:
            pass

        return _Dummy()

    monkeypatch.setattr(simulation_module.asyncio, "create_task", fake_create_task)

    res = await distribute_files(
        FileDistributeRequest(version_id=version.id, selected_paths=[], mode="pull"),
        db=db_session,
        student_id=test_student.id,
    )

    assert res.status_code == 202
    payload = json.loads(res.body.decode())
    assert payload["code"] == 0
    data = payload["data"]
    assert data["task_id"] is not None
    assert data["task_status"] == "PENDING"
    assert data["target_dir"] == "/home/student/experiment"

    # 验证任务已写入数据库
    task = await simulation_task_crud.get_task(db_session, data["task_id"])
    assert task is not None
    assert task.student_id == test_student.id


# ── 9. 分发全选语义 ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_distribute_full_selection_when_selected_paths_empty(db_session, test_student, monkeypatch):
    """分发全选语义：selected_paths=[] 时，后台任务应收到清单中全部文件。"""
    from contextlib import asynccontextmanager
    import app.api.v1.endpoints.student.simulation as simulation_module
    from app.api.v1.endpoints.student.simulation import distribute_files
    from app.schemas.experiment import FileDistributeRequest

    version, _ = await _setup_published_version_with_bundle(db_session, "dist_fullsel_exp")

    captured: list = []

    async def spy_distribute(files, student_id):
        captured.extend(files)

    monkeypatch.setattr(simulation_module, "_do_file_distribute", spy_distribute)

    @asynccontextmanager
    async def fake_session():
        yield db_session

    monkeypatch.setattr(simulation_module, "AsyncSessionLocal", fake_session)

    # 先创建任务（绕过 asyncio.create_task，直接运行后台协程）
    task = await simulation_task_crud.create_task(
        db_session, student_id=test_student.id, target_version_id=version.id, container_id=None
    )
    await simulation_module._run_distribute_task(task.task_id, test_student.id, list(SAMPLE_MANIFEST))

    assert len(captured) == len(SAMPLE_MANIFEST)
    captured_paths = {item["relative_path"] for item in captured}
    assert captured_paths == {item["relative_path"] for item in SAMPLE_MANIFEST}

    await db_session.refresh(task)
    assert task.status == SimulationTaskStatus.SUCCEEDED


# ── 10. 分发白名单与清单校验 ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_distribute_rejects_path_traversal(db_session, test_student, monkeypatch):
    """分发白名单：selected_paths 含 '../' 路径遍历应返回 400 INVALID_PATH。"""
    from app.api.v1.endpoints.student.simulation import distribute_files
    from app.schemas.experiment import FileDistributeRequest

    version, _ = await _setup_published_version_with_bundle(db_session, "dist_traversal_exp")

    with pytest.raises(HTTPException) as exc_info:
        await distribute_files(
            FileDistributeRequest(
                version_id=version.id,
                selected_paths=["../etc/passwd"],
                mode="pull",
            ),
            db=db_session,
            student_id=test_student.id,
        )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "INVALID_PATH"


@pytest.mark.asyncio
async def test_distribute_rejects_path_not_in_manifest(db_session, test_student, monkeypatch):
    """分发白名单：selected_paths 中的路径不在清单内应返回 400 PATH_NOT_IN_MANIFEST。"""
    from app.api.v1.endpoints.student.simulation import distribute_files
    from app.schemas.experiment import FileDistributeRequest

    version, _ = await _setup_published_version_with_bundle(db_session, "dist_notinmani_exp")

    with pytest.raises(HTTPException) as exc_info:
        await distribute_files(
            FileDistributeRequest(
                version_id=version.id,
                selected_paths=["secret/private_key.pem"],
                mode="pull",
            ),
            db=db_session,
            student_id=test_student.id,
        )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "PATH_NOT_IN_MANIFEST"


# ── 11. 分发权限修复失败 → retryable ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_distribute_permission_failure_marks_task_retryable(db_session, test_student, monkeypatch):
    """分发权限修复：_do_set_permissions 失败时，任务应标记为 FAILED + retryable。"""
    from contextlib import asynccontextmanager
    import app.api.v1.endpoints.student.simulation as simulation_module

    version, _ = await _setup_published_version_with_bundle(db_session, "dist_perm_exp")

    async def broken_permissions(student_id):
        raise RuntimeError("chmod: Operation not permitted")

    monkeypatch.setattr(simulation_module, "_do_set_permissions", broken_permissions)

    @asynccontextmanager
    async def fake_session():
        yield db_session

    monkeypatch.setattr(simulation_module, "AsyncSessionLocal", fake_session)

    task = await simulation_task_crud.create_task(
        db_session, student_id=test_student.id, target_version_id=version.id, container_id=None
    )
    await simulation_module._run_distribute_task(task.task_id, test_student.id, list(SAMPLE_MANIFEST))

    await db_session.refresh(task)
    assert task.status == SimulationTaskStatus.FAILED
    assert task.retryable is True
    assert task.error_code == "FILE_BUNDLE_DISTRIBUTION_FAILED"


# ── Error Path: 文件分发失败（_do_file_distribute 抛异常）─────────────────────

@pytest.mark.asyncio
async def test_distribute_file_copy_failure_marks_task_failed(db_session, test_student, monkeypatch):
    """Error Path 文件分发失败：_do_file_distribute 失败时，任务 FAILED + retryable + error_code 正确。"""
    from contextlib import asynccontextmanager
    import app.api.v1.endpoints.student.simulation as simulation_module

    version, _ = await _setup_published_version_with_bundle(db_session, "dist_copyfail_exp")

    async def broken_distribute(files, student_id):
        raise OSError("docker cp: container not running")

    monkeypatch.setattr(simulation_module, "_do_file_distribute", broken_distribute)

    @asynccontextmanager
    async def fake_session():
        yield db_session

    monkeypatch.setattr(simulation_module, "AsyncSessionLocal", fake_session)

    task = await simulation_task_crud.create_task(
        db_session, student_id=test_student.id, target_version_id=version.id, container_id=None
    )
    await simulation_module._run_distribute_task(task.task_id, test_student.id, list(SAMPLE_MANIFEST))

    await db_session.refresh(task)
    assert task.status == SimulationTaskStatus.FAILED
    assert task.retryable is True
    assert task.error_code == "FILE_BUNDLE_DISTRIBUTION_FAILED"
    assert "docker cp" in (task.error_message or "")


# ── Error Path: 健康检查失败 → 任务 FAILED + retryable ────────────────────────

@pytest.mark.asyncio
async def test_rebuild_task_fails_when_health_check_fails(db_session, test_student, monkeypatch):
    """Error Path 健康检查：容器状态为 error 时，重建任务应标记 FAILED + retryable。"""
    from contextlib import asynccontextmanager
    import app.api.v1.endpoints.student.simulation as simulation_module
    from app.models.container import ContainerStatus, SimContainer

    exp = await experiment_crud.create_experiment(
        db_session,
        name="健康失败实验",
        code="health_fail_exp",
        description=None,
        created_by=1,
    )
    version = await experiment_crud.create_version(
        db_session,
        experiment_id=exp.id,
        version_name="v1.0.0",
        environment_key="ros-health-fail",
        image_name="gzweb_sim:v1",
        launch_file_path="/launch/nav.launch",
        launch_args_template={},
        startup_script_ref=None,
        file_bundle_id=None,
        is_visible=True,
    )
    await experiment_crud.publish_version(
        db_session, experiment_id=exp.id, version=version, operator_id=1, note=None
    )

    task = await simulation_task_crud.create_task(
        db_session, student_id=test_student.id, target_version_id=version.id, container_id=None
    )

    # 模拟容器创建返回 error 状态（健康检查失败）
    error_container = SimContainer(
        user_id=test_student.id,
        image_name=version.image_name,
        status=ContainerStatus.ERROR,
        gzbridge_port=38080,
        rosbridge_port=39090,
        container_id="fake_error_container",
        error_message="健康检查超时",
    )

    async def fake_get_container_by_user(*args, **kwargs):
        return None

    async def fake_delete_container(*args, **kwargs):
        return True

    async def fake_create_container(*args, **kwargs):
        return error_container

    monkeypatch.setattr(simulation_module.crud_container, "get_container_by_user", fake_get_container_by_user)
    monkeypatch.setattr(simulation_module.crud_container, "delete_container", fake_delete_container)
    monkeypatch.setattr(simulation_module.crud_container, "create_container", fake_create_container)

    @asynccontextmanager
    async def fake_session():
        yield db_session

    monkeypatch.setattr(simulation_module, "AsyncSessionLocal", fake_session)

    await simulation_module._run_rebuild_task(task.task_id, test_student.id, version.id)

    await db_session.refresh(task)
    assert task.status == SimulationTaskStatus.FAILED
    assert task.retryable is True
    assert task.error_code == "CONTAINER_REBUILD_FAILED"


@pytest.mark.asyncio
async def test_rebuild_task_fails_immediately_when_container_exits_before_gz_ready(
    db_session, test_student, monkeypatch
):
    """Error Path：容器在 GZWEB 检测期间已退出，应立即失败，不等待端口超时。"""
    from contextlib import asynccontextmanager
    import app.api.v1.endpoints.student.simulation as simulation_module

    exp = await experiment_crud.create_experiment(
        db_session,
        name="容器提前退出实验",
        code="container_exit_before_gz",
        description=None,
        created_by=1,
    )
    version = await experiment_crud.create_version(
        db_session,
        experiment_id=exp.id,
        version_name="v1.0.0",
        environment_key="ros-exit-before-gz",
        image_name="gzweb_sim:v1",
        launch_file_path="/launch/nav.launch",
        launch_args_template={},
        startup_script_ref=None,
        file_bundle_id=None,
        is_visible=True,
    )
    await experiment_crud.publish_version(
        db_session, experiment_id=exp.id, version=version, operator_id=1, note=None
    )

    task = await simulation_task_crud.create_task(
        db_session, student_id=test_student.id, target_version_id=version.id, container_id=None
    )

    running_container = SimContainer(
        user_id=test_student.id,
        image_name=version.image_name,
        status=ContainerStatus.RUNNING,
        gzbridge_port=38081,
        rosbridge_port=39091,
        container_id="fake_running_container",
    )

    async def fake_get_container_by_user(*args, **kwargs):
        return None

    async def fake_delete_container(*args, **kwargs):
        return True

    async def fake_create_container(*args, **kwargs):
        return running_container

    async def fake_inspect_container_state(*args, **kwargs):
        return {
            "status": "exited",
            "exit_code": 1,
            "error": "",
            "oom_killed": False,
            "finished_at": "2026-01-01T00:00:00Z",
        }

    async def fake_get_logs_tail(*args, **kwargs):
        return "[entrypoint] startup failed: launch file missing"

    async def fake_check_port_ready(*args, **kwargs):
        return False, 0.0

    monkeypatch.setattr(simulation_module.crud_container, "get_container_by_user", fake_get_container_by_user)
    monkeypatch.setattr(simulation_module.crud_container, "delete_container", fake_delete_container)
    monkeypatch.setattr(simulation_module.crud_container, "create_container", fake_create_container)
    monkeypatch.setattr(simulation_module.container_manager, "inspect_container_state", fake_inspect_container_state)
    monkeypatch.setattr(simulation_module.container_manager, "get_container_logs_tail", fake_get_logs_tail)
    monkeypatch.setattr(simulation_module, "check_port_ready", fake_check_port_ready)

    @asynccontextmanager
    async def fake_session():
        yield db_session

    monkeypatch.setattr(simulation_module, "AsyncSessionLocal", fake_session)

    await simulation_module._run_rebuild_task(task.task_id, test_student.id, version.id)

    await db_session.refresh(task)
    assert running_container.status == ContainerStatus.STOPPED
    assert "docker_status=exited" in (running_container.error_message or "")
    assert task.status == SimulationTaskStatus.FAILED
    assert task.retryable is True
    assert task.error_code == "CONTAINER_REBUILD_FAILED"
    assert task.error_message == "CONTAINER_EXITED_BEFORE_GZWEB_READY"


@pytest.mark.asyncio
async def test_start_simulation_does_not_reuse_exited_running_container(db_session, test_student, monkeypatch):
    """即使 DB 里还是 running，只要 Docker 实际已退出，也不能直接复用。"""
    import app.api.v1.endpoints.student.simulation as simulation_module

    exp = await experiment_crud.create_experiment(
        db_session,
        name="退出容器复用保护实验",
        code="reuse_exited_guard_exp",
        description=None,
        created_by=1,
    )
    version = await experiment_crud.create_version(
        db_session,
        experiment_id=exp.id,
        version_name="v1.0.0",
        environment_key="ros-reuse-exited-guard",
        image_name="gzweb_sim:v1",
        launch_file_path="/launch/nav.launch",
        launch_args_template={},
        startup_script_ref=None,
        file_bundle_id=None,
        is_visible=True,
    )
    await experiment_crud.publish_version(
        db_session, experiment_id=exp.id, version=version, operator_id=1, note=None
    )

    stale_running_container = SimContainer(
        user_id=test_student.id,
        image_name=version.image_name,
        status=ContainerStatus.RUNNING,
        gzbridge_port=38082,
        rosbridge_port=39092,
        container_id="fake_stale_running_container",
        current_version_id=version.id,
    )

    async def fake_get_container_by_user(*args, **kwargs):
        return stale_running_container

    async def fake_inspect_container_state(*args, **kwargs):
        return {
            "status": "exited",
            "exit_code": 1,
            "error": "",
            "oom_killed": False,
            "finished_at": "2026-01-01T00:00:00Z",
        }

    def fake_create_task(coro):
        coro.close()

        class _DummyTask:
            pass

        return _DummyTask()

    monkeypatch.setattr(simulation_module.crud_container, "get_container_by_user", fake_get_container_by_user)
    monkeypatch.setattr(simulation_module.container_manager, "inspect_container_state", fake_inspect_container_state)
    monkeypatch.setattr(simulation_module.asyncio, "create_task", fake_create_task)

    res = await simulation_module.start_simulation(
        StudentSimulationStartRequest(version_id=version.id, force_recreate=False),
        db=db_session,
        student_id=test_student.id,
    )

    assert res.status_code == 202
    payload = json.loads(res.body.decode("utf-8"))
    assert payload["code"] == 0
    assert payload["data"]["container_status"] == "creating"
    assert payload["data"]["task_id"] is not None
    assert stale_running_container.status == ContainerStatus.STOPPED
    assert stale_running_container.error_message == "docker_status=exited exit_code=1"
