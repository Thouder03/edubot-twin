import pytest

import app.api.v1.endpoints.student.terminal as terminal_module


class _DummyProc:
    def __init__(self, returncode: int, stdout: bytes = b"", stderr: bytes = b""):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self):
        return self._stdout, self._stderr


@pytest.mark.asyncio
async def test_ensure_experiment_dir_permissions_success(monkeypatch):
    calls: list[tuple] = []

    async def fake_create_subprocess_exec(*args, **kwargs):
        calls.append(args)
        return _DummyProc(returncode=0)

    monkeypatch.setattr(terminal_module.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    await terminal_module._ensure_experiment_dir_permissions("container-abc")

    assert len(calls) == 1
    args = calls[0]
    assert args[0] == "docker"
    assert args[1] == "exec"
    assert args[2] == "container-abc"
    assert args[3] == "bash"
    assert args[4] == "-lc"
    assert "/home/student/experiment" in args[5]


@pytest.mark.asyncio
async def test_ensure_experiment_dir_permissions_failure(monkeypatch):
    async def fake_create_subprocess_exec(*args, **kwargs):
        return _DummyProc(returncode=1, stderr=b"chmod: Operation not permitted")

    monkeypatch.setattr(terminal_module.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    with pytest.raises(RuntimeError, match="Operation not permitted"):
        await terminal_module._ensure_experiment_dir_permissions("container-abc")
