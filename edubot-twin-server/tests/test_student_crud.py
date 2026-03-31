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
