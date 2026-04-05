import pytest

from app.crud import experiment as experiment_crud
from app.api.v1.endpoints.teacher.experiments import (
    switch_experiment_status as switch_experiment_status_endpoint,
    switch_version_publish_status as switch_version_publish_status_endpoint,
)
from app.schemas.experiment import (
    ExperimentStatusSwitchRequest,
    ExperimentVersionPublishStatusRequest,
)


@pytest.mark.asyncio
async def test_switch_experiment_status_allows_active_to_draft_in_crud(db_session):
    """回归测试：实验状态机应允许 active -> draft。"""
    exp = await experiment_crud.create_experiment(
        db_session,
        name="状态切换回归实验",
        code="status_toggle_crud_exp",
        description="验证 active 回退 draft",
        created_by=1,
    )

    exp = await experiment_crud.switch_experiment_status(
        db_session,
        experiment=exp,
        new_status="active",
    )
    assert exp.status.value == "active"

    exp = await experiment_crud.switch_experiment_status(
        db_session,
        experiment=exp,
        new_status="draft",
    )
    assert exp.status.value == "draft"


@pytest.mark.asyncio
async def test_switch_experiment_status_allows_active_to_draft_in_endpoint(db_session):
    """回归测试：教师端状态切换接口应允许 active -> draft。"""
    exp = await experiment_crud.create_experiment(
        db_session,
        name="状态切换接口回归实验",
        code="status_toggle_endpoint_exp",
        description="验证接口 active 回退 draft",
        created_by=1,
    )

    await experiment_crud.switch_experiment_status(
        db_session,
        experiment=exp,
        new_status="active",
    )

    res = await switch_experiment_status_endpoint(
        experiment_id=exp.id,
        data=ExperimentStatusSwitchRequest(status="draft"),
        db=db_session,
        _=1,
    )

    assert res.code == 0
    assert res.data is not None
    assert res.data["experiment_id"] == exp.id
    assert res.data["status"] == "draft"


@pytest.mark.asyncio
async def test_switch_version_publish_status_allows_arbitrary_transition_in_crud(db_session):
    """回归测试：版本状态应支持任意切换（含 published -> draft）。"""
    exp = await experiment_crud.create_experiment(
        db_session,
        name="版本状态任意切换实验",
        code="version_status_toggle_crud_exp",
        description="验证版本状态任意切换",
        created_by=1,
    )

    version = await experiment_crud.create_version(
        db_session,
        experiment_id=exp.id,
        version_name="v1.0.0",
        environment_key="sim_env",
        image_name="gzweb_sim:v1",
        launch_file_path="/launch/main.launch",
        launch_args_template={},
        file_bundle_id=None,
        env_bundle_id=None,
    )
    assert version.publish_status.value == "draft"

    version = await experiment_crud.switch_version_publish_status(
        db_session,
        version=version,
        new_status="deprecated",
        operator_id=1,
    )
    assert version.publish_status.value == "deprecated"

    version = await experiment_crud.switch_version_publish_status(
        db_session,
        version=version,
        new_status="published",
        operator_id=1,
        publish_note="测试发布",
    )
    assert version.publish_status.value == "published"

    version = await experiment_crud.switch_version_publish_status(
        db_session,
        version=version,
        new_status="draft",
        operator_id=1,
    )
    assert version.publish_status.value == "draft"


@pytest.mark.asyncio
async def test_switch_version_publish_status_allows_arbitrary_transition_in_endpoint(db_session):
    """回归测试：接口层应支持版本状态任意切换（含 published -> draft）。"""
    exp = await experiment_crud.create_experiment(
        db_session,
        name="版本状态任意切换接口实验",
        code="version_status_toggle_endpoint_exp",
        description="验证接口版本状态任意切换",
        created_by=1,
    )

    version = await experiment_crud.create_version(
        db_session,
        experiment_id=exp.id,
        version_name="v1.0.1",
        environment_key="sim_env",
        image_name="gzweb_sim:v1",
        launch_file_path="/launch/main.launch",
        launch_args_template={},
        file_bundle_id=None,
        env_bundle_id=None,
    )

    res1 = await switch_version_publish_status_endpoint(
        experiment_id=exp.id,
        version_id=version.id,
        data=ExperimentVersionPublishStatusRequest(
            publish_status="deprecated",
            publish_note="接口改为废弃",
        ),
        db=db_session,
        teacher_id=1,
    )
    assert res1.code == 0
    assert res1.data is not None
    assert res1.data["publish_status"] == "deprecated"

    res2 = await switch_version_publish_status_endpoint(
        experiment_id=exp.id,
        version_id=version.id,
        data=ExperimentVersionPublishStatusRequest(
            publish_status="published",
            publish_note="接口改为发布",
        ),
        db=db_session,
        teacher_id=1,
    )
    assert res2.code == 0
    assert res2.data is not None
    assert res2.data["publish_status"] == "published"

    res3 = await switch_version_publish_status_endpoint(
        experiment_id=exp.id,
        version_id=version.id,
        data=ExperimentVersionPublishStatusRequest(
            publish_status="draft",
            publish_note="接口回退草稿",
        ),
        db=db_session,
        teacher_id=1,
    )
    assert res3.code == 0
    assert res3.data is not None
    assert res3.data["publish_status"] == "draft"
