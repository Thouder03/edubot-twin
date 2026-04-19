from types import SimpleNamespace

import pytest
from app.crud import student as student_crud
from app.schemas.student import StudentCreate, StudentUpdate

@pytest.mark.asyncio
async def test_create_student(db_session):
    student_in = StudentCreate(username="new_user", password="pass123", real_name="New User")
    student = await student_crud.create_student(db_session, student_in)
    assert student.username == "new_user"
    assert student.real_name == "New User"
    assert student.role_code == "student"
    assert student.role_id == "10"

@pytest.mark.asyncio
async def test_get_student(db_session, test_student):
    student = await student_crud.get_student(db_session, test_student.id)
    assert student.id == test_student.id

@pytest.mark.asyncio
async def test_get_student_by_username(db_session, test_student):
    student = await student_crud.get_student_by_username(db_session, "test_user")
    assert student.username == "test_user"

@pytest.mark.asyncio
async def test_update_student(db_session, test_student):
    update_data = StudentUpdate(real_name="Updated Name")
    updated = await student_crud.update_student(db_session, test_student.id, update_data)
    assert updated.real_name == "Updated Name"

@pytest.mark.asyncio
async def test_delete_student(db_session, test_student):
    result = await student_crud.delete_student(db_session, test_student.id)
    assert result is True
    student = await student_crud.get_student(db_session, test_student.id)
    assert student is None


@pytest.mark.asyncio
async def test_create_student_with_explicit_teacher_role(db_session):
    teacher_in = StudentCreate(
        username="teacher_user",
        password="pass123",
        real_name="Teacher User",
        role_id="20",
        role_code="teacher",
    )
    teacher = await student_crud.create_student(db_session, teacher_in)
    assert teacher.username == "teacher_user"
    assert teacher.role_code == "teacher"
    assert teacher.role_id == "20"


@pytest.mark.asyncio
async def test_delete_student_endpoint_also_deletes_workspace(db_session, test_student, monkeypatch, tmp_path):
    from app.api.v1.endpoints.teacher import students as teacher_students_endpoint

    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "main.py").write_text("print('hello')")

    monkeypatch.setattr(
        teacher_students_endpoint.path_policy,
        "get_student_workspace_host_dir",
        lambda _student_id: workspace_dir,
    )

    fake_docker_client = SimpleNamespace(containers=SimpleNamespace())
    monkeypatch.setattr(
        teacher_students_endpoint,
        "get_docker_client",
        lambda: fake_docker_client,
    )

    res = await teacher_students_endpoint.delete_student(
        student_id=test_student.id,
        db=db_session,
        _={"id": 1, "role_code": "teacher"},
    )

    assert res.code == 0
    assert res.data["deleted"] is True
    assert res.data["workspace_deleted"] is True
    assert not workspace_dir.exists()

    student = await student_crud.get_student(db_session, test_student.id)
    assert student is None


@pytest.mark.asyncio
async def test_delete_student_endpoint_workspace_delete_failure_blocks_db_delete(db_session, test_student, monkeypatch, tmp_path):
    from fastapi import HTTPException
    from app.api.v1.endpoints.teacher import students as teacher_students_endpoint

    workspace_dir = tmp_path / "workspace-fail"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "main.py").write_text("print('hello')")

    monkeypatch.setattr(
        teacher_students_endpoint.path_policy,
        "get_student_workspace_host_dir",
        lambda _student_id: workspace_dir,
    )

    fake_docker_client = SimpleNamespace(containers=SimpleNamespace())
    monkeypatch.setattr(
        teacher_students_endpoint,
        "get_docker_client",
        lambda: fake_docker_client,
    )

    def _raise_os_error(_path):
        raise OSError("mock remove failed")

    monkeypatch.setattr(teacher_students_endpoint.shutil, "rmtree", _raise_os_error)

    with pytest.raises(HTTPException) as exc_info:
        await teacher_students_endpoint.delete_student(
            student_id=test_student.id,
            db=db_session,
            _={"id": 1, "role_code": "teacher"},
        )

    assert exc_info.value.status_code == 500
    assert "工作区删除失败" in str(exc_info.value.detail)

    student = await student_crud.get_student(db_session, test_student.id)
    assert student is not None
