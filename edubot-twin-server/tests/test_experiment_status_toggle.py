import pytest

from app.crud import experiment as experiment_crud
from app.api.v1.endpoints.teacher.experiments import (
    switch_experiment_status as switch_experiment_status_endpoint,
)
from app.schemas.experiment import ExperimentStatusSwitchRequest


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
