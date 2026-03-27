import pytest
from app.core.security import create_access_token, verify_token, get_current_teacher
from fastapi import HTTPException

def test_create_access_token():
    token = create_access_token({"sub": "1", "role": "teacher"})
    assert isinstance(token, str)
    assert len(token) > 0

def test_verify_token():
    token = create_access_token({"sub": "1", "role": "teacher"})
    payload = verify_token(token)
    assert payload["sub"] == "1"
    assert payload["role"] == "teacher"

def test_verify_invalid_token():
    payload = verify_token("invalid_token")
    assert payload is None

@pytest.mark.asyncio
async def test_get_current_teacher_valid():
    token = create_access_token({"user_id": "1", "role": "teacher", "username": "teacher1"})
    result = await get_current_teacher(f"Bearer {token}")
    assert result == "1"

@pytest.mark.asyncio
async def test_get_current_teacher_invalid_role():
    token = create_access_token({"user_id": "1", "role": "student"})
    with pytest.raises(HTTPException) as exc:
        await get_current_teacher(f"Bearer {token}")
    assert exc.value.status_code == 403
