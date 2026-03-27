import pytest
from app.crud import container as container_crud
from app.models.container import ContainerStatus

@pytest.mark.asyncio
async def test_get_containers_by_student(db_session, test_student):
    containers = await container_crud.get_containers_by_student(db_session, test_student.id)
    assert isinstance(containers, list)

@pytest.mark.asyncio
async def test_get_container_by_student(db_session, test_student):
    container = await container_crud.get_container_by_student(db_session, test_student.id)
    assert container is None or container.student_id == test_student.id
