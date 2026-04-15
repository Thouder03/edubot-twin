from contextlib import asynccontextmanager
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

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


@pytest.mark.asyncio
async def test_orphan_reconcile_removes_db_record_when_docker_missing(db_session, monkeypatch):
    """回归测试：阶段 B 发现物理容器不存在时，应删除 DB 孤儿记录。"""
    import app.main as main_module

    container = SimContainer(
        container_id="orphan-db-only-container",
        user_id=1,
        image_name="edubot/gazebo-ros:latest",
        status=ContainerStatus.RUNNING,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(container)
    await db_session.commit()
    await db_session.refresh(container)

    @asynccontextmanager
    async def fake_session():
        yield db_session

    async def fake_find_zombie_state_containers(_db, timeout_seconds):
        return []

    async def fake_find_active_db_containers(_db):
        result = await _db.execute(
            select(SimContainer).where(SimContainer.id == container.id)
        )
        target = result.scalar_one_or_none()
        return [target] if target else []

    async def fake_inspect_container(_container_id):
        return None

    async def fake_list_edubot_simulation_containers():
        return []

    async def fake_get_known_container_ids(_db):
        return set()

    monkeypatch.setattr(main_module, "AsyncSessionLocal", fake_session)
    monkeypatch.setattr(
        main_module.crud_container,
        "find_zombie_state_containers",
        fake_find_zombie_state_containers,
    )
    monkeypatch.setattr(
        main_module.crud_container,
        "find_active_db_containers",
        fake_find_active_db_containers,
    )
    monkeypatch.setattr(main_module, "inspect_container", fake_inspect_container)
    monkeypatch.setattr(
        main_module,
        "list_edubot_simulation_containers",
        fake_list_edubot_simulation_containers,
    )
    monkeypatch.setattr(
        main_module.crud_container,
        "get_known_container_ids",
        fake_get_known_container_ids,
    )

    stats = await main_module._orphan_container_reconcile_once()

    deleted = await container_crud.get_container(db_session, container.id)
    assert deleted is None
    assert stats["db_corrected"] == 1
