import pytest
from app.core.security import create_access_token

@pytest.fixture
def teacher_token():
    return create_access_token({"sub": "1", "role": "teacher"})

def test_teacher_token_creation(teacher_token):
    assert isinstance(teacher_token, str)
    assert len(teacher_token) > 0
