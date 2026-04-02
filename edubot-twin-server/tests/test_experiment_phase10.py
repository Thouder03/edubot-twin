import pytest

from app.crud import experiment as experiment_crud
from app.models.container import ContainerStatus, SimContainer
from app.models.experiment import PublishStatus
from app.schemas.experiment import StudentSimulationStartRequest
from app.api.v1.endpoints.student.simulation import start_simulation


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

    res = await start_simulation(
        StudentSimulationStartRequest(version_id=version.id, force_recreate=False),
        db=db_session,
        student_id=test_student.id,
    )

    assert res.code == 0
    assert res.data is not None
    assert res.data.container_status == "running"
    assert res.data.experiment_context["environment_key"] == "ros-noetic-recreate"
    assert res.data.experiment_context["version_id"] == version.id
