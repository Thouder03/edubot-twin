import pytest
from app.core.logger import log_container_event

def test_log_container_event():
    log_container_event("test_event", container_id=1, student_id=1, message="Test log")
    # 日志函数不抛出异常即为成功
    assert True
