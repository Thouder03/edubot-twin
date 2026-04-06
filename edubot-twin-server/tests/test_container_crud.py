from datetime import datetime, timedelta

import pytest
from app.core.port_allocator import allocate_ports
from app.crud import container as container_crud
from app.models.container import ContainerStatus, SimContainer

@pytest.mark.asyncio
async def test_get_containers_by_student(db_session, test_student):
    containers = await container_crud.get_containers_by_student(db_session, test_student.id)
    assert isinstance(containers, list)

@pytest.mark.asyncio
async def test_get_container_by_student(db_session, test_student):
    container = await container_crud.get_container_by_student(db_session, test_student.id)
    assert container is None or container.student_id == test_student.id


@pytest.mark.asyncio
async def test_find_stale_containers_does_not_flag_new_running_without_heartbeat(db_session):
    """回归测试：新建 running 容器在首心跳前不应被误判超时。"""
    now = datetime.utcnow()
    fresh_container = SimContainer(
      container_id="fresh-no-heartbeat",
      user_id=1,
      image_name="edubot/gazebo-ros:latest",
      status=ContainerStatus.RUNNING,
      last_heartbeat_at=None,
      created_at=now,
      updated_at=now,
    )
    db_session.add(fresh_container)
    await db_session.commit()

    stale = await container_crud.find_stale_containers(db_session, timeout_seconds=120)
    stale_ids = {c.container_id for c in stale}

    assert "fresh-no-heartbeat" not in stale_ids


@pytest.mark.asyncio
async def test_find_stale_containers_flags_old_running_without_heartbeat(db_session):
    """回归测试：长期无心跳的 running 容器仍应被判定超时。"""
    old_time = datetime.utcnow() - timedelta(seconds=300)
    old_container = SimContainer(
      container_id="old-no-heartbeat",
      user_id=1,
      image_name="edubot/gazebo-ros:latest",
      status=ContainerStatus.RUNNING,
      last_heartbeat_at=None,
      created_at=old_time,
      updated_at=old_time,
    )
    db_session.add(old_container)
    await db_session.commit()

    stale = await container_crud.find_stale_containers(db_session, timeout_seconds=120)
    stale_ids = {c.container_id for c in stale}

    assert "old-no-heartbeat" in stale_ids


@pytest.mark.asyncio
async def test_allocate_ports_skips_stopping_container_ports(db_session):
    """回归测试：stopping 容器仍应占用端口，避免新容器复用到竞态端口。"""
    now = datetime.utcnow()
    stopping_container = SimContainer(
        container_id="stopping-port-holder",
        user_id=1,
        image_name="edubot/gazebo-ros:latest",
        status=ContainerStatus.STOPPING,
        gzbridge_port=9000,
        rosbridge_port=9500,
        created_at=now,
        updated_at=now,
    )
    db_session.add(stopping_container)
    await db_session.commit()

    gz_port, ros_port = await allocate_ports(db_session)

    assert gz_port != 9000
    assert ros_port != 9500
