import pytest
from pydantic import ValidationError
from app.schemas.container import ContainerCreate
from app.schemas.student import StudentCreate

def test_container_cpu_validation():
    with pytest.raises(ValidationError):
        ContainerCreate(student_id=1, cpu_limit=5.0, memory_limit=512)

def test_container_memory_validation():
    with pytest.raises(ValidationError):
        ContainerCreate(student_id=1, cpu_limit=1.0, memory_limit=100)

def test_valid_container_create():
    container = ContainerCreate(student_id=1, cpu_limit=2.0, memory_limit=1024)
    assert container.cpu_limit == 2.0
    assert container.memory_limit == 1024

def test_student_create_validation():
    student = StudentCreate(username="test", password="pass123", real_name="Test")
    assert student.username == "test"
    assert student.real_name == "Test"
