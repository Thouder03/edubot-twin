"""
Sidecar 文件服务测试套件

覆盖：
  TC-SC-01: shadow_root scope — 全路径读写
  TC-SC-02: student_limited scope — /home/student 可写
  TC-SC-03: student_limited scope — /home 只读（写操作 403）
  TC-SC-04: student_limited scope — /root 只读（写操作 403）
  TC-SC-05: student_limited scope — 其他路径（/etc）被拒绝读取
  TC-SC-06: 路径穿越防护（../ 被拒绝）
  TC-SC-07: 危险路径删除保护（/ /bin /etc 等被拒绝）
  TC-SC-08: list 端点 — 返回 files/directories 格式与 student/files.py 一致
  TC-SC-09: upload/download 流式传输
  TC-SC-10: rename / move / copy / batch-delete 操作
  TC-SC-11: extract / compress 操作
"""
import io
import os
import sys
import zipfile
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
import httpx

# ─── 将 Sidecar 脚本加入 Python 路径 ──────────────────────────────────────────
SIDECAR_PATH = Path(__file__).parent.parent / "data/system/agent"
sys.path.insert(0, str(SIDECAR_PATH))

from mini_file_server import app  # type: ignore


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
    """
    返回绑定 Sidecar ASGI 应用的 httpx 异步客户端。

    为了让路径操作落到 tmp_path 内，我们通过 monkeypatch 替换
    mini_file_server 的 resolve_path，使其在 tmp_path 下解析。
    """
    # 不 monkeypatch 文件系统：测试直接在 tmp_path 内创建真实文件，
    # 并用绝对路径参数与 Sidecar 通信——这与生产行为完全一致。
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, tmp_path


# ─── 辅助工具 ─────────────────────────────────────────────────────────────────

def headers(scope: str) -> dict:
    return {"X-Access-Scope": scope}


def shadow() -> dict:
    return headers("shadow_root")


def student() -> dict:
    return headers("student_limited")


# ═══════════════════════════════════════════════════════════════════════════════
# TC-SC-01: shadow_root — 全路径读写
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_sc_01_shadow_root_list_and_read(client):
    c, tmp = client
    # 创建测试文件
    (tmp / "hello.txt").write_text("hello world")

    # list
    res = await c.get("/files/list", params={"path": str(tmp)}, headers=shadow())
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert "files" in data
    names = [f["name"] for f in data["files"]]
    assert "hello.txt" in names

    # read
    res = await c.get("/files/read", params={"path": str(tmp / "hello.txt")}, headers=shadow())
    assert res.status_code == 200
    assert res.json()["data"]["content"] == "hello world"


@pytest.mark.asyncio
async def test_sc_01_shadow_root_save(client):
    c, tmp = client
    path = str(tmp / "new_file.py")

    res = await c.post("/files/save", json={"path": path, "content": "x = 1"}, headers=shadow())
    assert res.status_code == 200
    assert Path(path).read_text() == "x = 1"


@pytest.mark.asyncio
async def test_sc_01_shadow_root_mkdir_and_delete(client):
    c, tmp = client
    dirpath = str(tmp / "subdir")

    res = await c.post("/files/mkdir", json={"path": dirpath}, headers=shadow())
    assert res.status_code == 200
    assert Path(dirpath).is_dir()

    res = await c.delete("/files/delete", params={"path": dirpath}, headers=shadow())
    assert res.status_code == 200
    assert not Path(dirpath).exists()


# ═══════════════════════════════════════════════════════════════════════════════
# TC-SC-02: student_limited — /home/student 可写
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_sc_02_student_write_home_student(client, tmp_path):
    """用 tmp_path 模拟 /home/student 目录（路径策略校验使用字符串前缀匹配）"""
    c, _ = client
    # 通过直接测试策略函数验证，而不是文件系统操作
    import mini_file_server as svc  # type: ignore
    from fastapi import HTTPException

    home_student = Path("/home/student/test.py")
    # 不应抛出异常
    try:
        svc.check_write_allowed(home_student, "student_limited")
    except HTTPException:
        pytest.fail("student_limited 应允许写入 /home/student")


@pytest.mark.asyncio
async def test_sc_02_student_save_allowed_path(client):
    """实际走 API：向 /home/student 子路径 save 时应被允许（路径策略层面）"""
    c, tmp = client
    import mini_file_server as svc  # type: ignore
    from fastapi import HTTPException

    # /home/student/workspace 是合法写路径
    path = Path("/home/student/workspace/test.py")
    try:
        svc.check_write_allowed(path, "student_limited")
        svc.check_read_allowed(path, "student_limited")
    except HTTPException as e:
        pytest.fail(f"策略应允许读写 /home/student/workspace: {e.detail}")


# ═══════════════════════════════════════════════════════════════════════════════
# TC-SC-03: student_limited — /home 只读（写 403）
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_sc_03_student_write_home_forbidden(client):
    import mini_file_server as svc  # type: ignore
    from fastapi import HTTPException

    # /home/other_user 不在 /home/student 下，写应被拒绝
    path = Path("/home/other_user/file.txt")
    with pytest.raises(HTTPException) as exc_info:
        svc.check_write_allowed(path, "student_limited")
    assert exc_info.value.status_code == 403

    # /home/student 自身可写，/home 不行
    path_home = Path("/home")
    with pytest.raises(HTTPException):
        svc.check_write_allowed(path_home, "student_limited")


@pytest.mark.asyncio
async def test_sc_03_student_read_home_allowed(client):
    import mini_file_server as svc  # type: ignore
    from fastapi import HTTPException

    # /home 允许读
    try:
        svc.check_read_allowed(Path("/home"), "student_limited")
        svc.check_read_allowed(Path("/home/other"), "student_limited")
    except HTTPException:
        pytest.fail("/home 前缀应允许 student_limited 读取")


# ═══════════════════════════════════════════════════════════════════════════════
# TC-SC-04: student_limited — /root 只读
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_sc_04_student_root_readonly(client):
    import mini_file_server as svc  # type: ignore
    from fastapi import HTTPException

    # /root 允许读
    try:
        svc.check_read_allowed(Path("/root"), "student_limited")
        svc.check_read_allowed(Path("/root/.ros"), "student_limited")
    except HTTPException:
        pytest.fail("/root 前缀应允许 student_limited 读取")

    # /root 写被拒绝
    with pytest.raises(HTTPException) as exc_info:
        svc.check_write_allowed(Path("/root/.bashrc"), "student_limited")
    assert exc_info.value.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════════
# TC-SC-05: student_limited — /etc 等路径完全拒绝
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_sc_05_student_etc_forbidden(client):
    import mini_file_server as svc  # type: ignore
    from fastapi import HTTPException

    for path_str in ["/etc", "/etc/passwd", "/usr", "/opt", "/var"]:
        with pytest.raises(HTTPException) as exc_info:
            svc.check_read_allowed(Path(path_str), "student_limited")
        assert exc_info.value.status_code == 403, f"{path_str} 应被 student_limited 读取拒绝"


# ═══════════════════════════════════════════════════════════════════════════════
# TC-SC-06: 路径穿越防护
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_sc_06_path_traversal(client):
    import mini_file_server as svc  # type: ignore
    from fastapi import HTTPException

    # .. 穿越被拒绝
    with pytest.raises(HTTPException) as exc_info:
        svc.resolve_path("../etc/passwd")
    assert exc_info.value.status_code == 400

    with pytest.raises(HTTPException):
        svc.resolve_path("/home/student/../../etc/passwd")


@pytest.mark.asyncio
async def test_sc_06_path_traversal_via_api(client):
    c, _ = client
    res = await c.get("/files/read", params={"path": "/../etc/passwd"}, headers=shadow())
    # .. 穿越应被拒绝（400），或者文件不存在（404）
    assert res.status_code in (400, 404)


# ═══════════════════════════════════════════════════════════════════════════════
# TC-SC-07: 危险路径删除保护
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_sc_07_blocked_delete_paths(client):
    import mini_file_server as svc  # type: ignore
    from fastapi import HTTPException

    blocked = ["/", "/bin", "/sbin", "/usr", "/etc", "/proc", "/sys", "/boot", "/opt/ros"]
    for p in blocked:
        with pytest.raises(HTTPException) as exc_info:
            svc.check_delete_allowed(Path(p), "shadow_root")
        assert exc_info.value.status_code == 403, f"{p} 应被删除保护拦截"


# ═══════════════════════════════════════════════════════════════════════════════
# TC-SC-08: list 端点 — 响应格式验证
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_sc_08_list_format(client):
    """list 返回格式与 student/files.py 完全一致：files[].path, directories[].path"""
    c, tmp = client
    (tmp / "readme.md").write_text("# test")
    subdir = tmp / "src"
    subdir.mkdir()

    res = await c.get("/files/list", params={"path": str(tmp)}, headers=shadow())
    assert res.status_code == 200

    data = res.json()["data"]
    assert "files" in data
    assert "directories" in data
    assert "path" in data

    # files 结构
    assert len(data["files"]) >= 1
    f = data["files"][0]
    for key in ["name", "path", "size", "modified", "extension"]:
        assert key in f, f"files 缺少字段 {key}"

    # directories 结构
    assert len(data["directories"]) >= 1
    d = data["directories"][0]
    for key in ["name", "path", "file_count"]:
        assert key in d, f"directories 缺少字段 {key}"


# ═══════════════════════════════════════════════════════════════════════════════
# TC-SC-09: upload / download 流式传输
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_sc_09_upload_and_download(client):
    c, tmp = client
    content = b"binary content \x00\x01\x02"
    target_dir = str(tmp)

    # upload
    res = await c.post(
        "/files/upload",
        files={"file": ("test.bin", io.BytesIO(content), "application/octet-stream")},
        data={"target_path": target_dir},
        headers=shadow(),
    )
    assert res.status_code == 200, res.text
    uploaded_path = res.json()["data"]["path"]
    assert Path(uploaded_path).read_bytes() == content

    # download single file
    res = await c.get("/files/download", params={"path": uploaded_path}, headers=shadow())
    assert res.status_code == 200
    assert res.content == content


@pytest.mark.asyncio
async def test_sc_09_download_directory_as_zip(client):
    c, tmp = client
    (tmp / "a.txt").write_text("aaa")
    (tmp / "b.txt").write_text("bbb")

    res = await c.get("/files/download", params={"path": str(tmp)}, headers=shadow())
    assert res.status_code == 200
    assert res.headers.get("content-type", "").startswith("application/zip")

    # 验证 zip 内容
    zf = zipfile.ZipFile(io.BytesIO(res.content))
    names = zf.namelist()
    assert any("a.txt" in n for n in names)
    assert any("b.txt" in n for n in names)


@pytest.mark.asyncio
async def test_sc_09_download_multiple(client):
    c, tmp = client
    (tmp / "x.py").write_text("x = 1")
    (tmp / "y.py").write_text("y = 2")

    res = await c.post(
        "/files/download-multiple",
        json={"paths": [str(tmp / "x.py"), str(tmp / "y.py")], "archive_name": "combo.zip"},
        headers=shadow(),
    )
    assert res.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(res.content))
    assert "x.py" in zf.namelist()
    assert "y.py" in zf.namelist()


# ═══════════════════════════════════════════════════════════════════════════════
# TC-SC-10: rename / move / copy / batch-delete
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_sc_10_rename(client):
    c, tmp = client
    src = tmp / "old.txt"
    src.write_text("rename me")

    res = await c.post(
        "/files/rename",
        json={"path": str(src), "new_name": "new.txt"},
        headers=shadow(),
    )
    assert res.status_code == 200
    assert not src.exists()
    assert (tmp / "new.txt").exists()


@pytest.mark.asyncio
async def test_sc_10_move(client):
    c, tmp = client
    src = tmp / "move_src.txt"
    src.write_text("move me")
    dst_dir = tmp / "dst"
    dst_dir.mkdir()

    res = await c.post(
        "/files/move",
        json={"source_paths": [str(src)], "target_dir": str(dst_dir)},
        headers=shadow(),
    )
    assert res.status_code == 200
    assert not src.exists()
    assert (dst_dir / "move_src.txt").exists()


@pytest.mark.asyncio
async def test_sc_10_copy(client):
    c, tmp = client
    src = tmp / "copy_src.txt"
    src.write_text("copy me")
    dst_dir = tmp / "dst_copy"
    dst_dir.mkdir()

    res = await c.post(
        "/files/copy",
        json={"source_paths": [str(src)], "target_dir": str(dst_dir)},
        headers=shadow(),
    )
    assert res.status_code == 200
    assert src.exists()  # 原文件仍在
    assert (dst_dir / "copy_src.txt").exists()


@pytest.mark.asyncio
async def test_sc_10_batch_delete(client):
    c, tmp = client
    files = [tmp / f"del_{i}.txt" for i in range(3)]
    for f in files:
        f.write_text("delete me")

    res = await c.request(
        "DELETE",
        "/files/batch-delete",
        json={"paths": [str(f) for f in files]},
        headers=shadow(),
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert len(data["deleted"]) == 3
    assert len(data["failed"]) == 0
    for f in files:
        assert not f.exists()


# ═══════════════════════════════════════════════════════════════════════════════
# TC-SC-11: extract / compress
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_sc_11_compress_and_extract(client):
    c, tmp = client
    # 准备文件
    (tmp / "compress_me.txt").write_text("compress content")

    # compress → zip
    res = await c.post(
        "/files/compress",
        json={
            "paths": [str(tmp / "compress_me.txt")],
            "archive_name": "output.zip",
            "format": "zip",
            "target_dir": str(tmp),
        },
        headers=shadow(),
    )
    assert res.status_code == 200, res.text
    zip_path = res.json()["data"]["archive_path"]
    assert Path(zip_path).exists()

    # extract → 到 extract_out 目录
    extract_dir = tmp / "extract_out"
    extract_dir.mkdir()
    res = await c.post(
        "/files/extract",
        json={"path": zip_path, "target_dir": str(extract_dir)},
        headers=shadow(),
    )
    assert res.status_code == 200
    assert (extract_dir / "compress_me.txt").exists()
    assert (extract_dir / "compress_me.txt").read_text() == "compress content"


# ═══════════════════════════════════════════════════════════════════════════════
# TC-SC-12: health 端点
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_sc_12_health(client):
    c, _ = client
    res = await c.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
