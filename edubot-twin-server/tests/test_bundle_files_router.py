"""
通用 Bundle 文件路由工厂测试（第11期补全）

通过 exam-env-snapshots 端点验证 12 个文件操作全部打通：
  list / upload / read / save / delete / mkdir / rename / move / copy /
  extract / compress / download

每个用例覆盖：
  - 工厂生成的路由正确绑定 FastAPI 路径参数
  - resolver / stats_updater 回调被正确调用（即 file_count / total_size_bytes 回写）
  - 路径穿越/404 等异常在 HTTP 层被正确映射
"""
import io
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token
from app.crud import exam_env_snapshot as crud_env_snap


TEACHER_ID = 1


async def _create_snapshot(db_session, monkeypatch, tmp_path: Path, name="rt"):
    """创建一个考试环境快照（绕过磁盘默认路径）"""
    monkeypatch.setattr(
        crud_env_snap, "EXAM_ENV_SNAPSHOTS_BASE_DIR", tmp_path / "exam_env_snapshots"
    )
    return await crud_env_snap.create_env_snapshot(
        db_session,
        name=f"factory_{name}",
        container_target_dir="/home/ubuntu20/catkin_ws",
        created_by=TEACHER_ID,
    )


def _url(snapshot_id: int, suffix: str = "") -> str:
    return f"/api/v1/teachers/exam-env-snapshots/{snapshot_id}/files{suffix}"


async def _client():
    from app.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _auth() -> dict:
    token = create_access_token({"user_id": TEACHER_ID, "role": "teacher"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def override_get_db(db_session):
    """把 FastAPI 的 get_db 依赖替换为 in-memory session，供 TestClient 使用"""
    from app.main import app
    from app.db.database import get_db

    async def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def mock_teacher_auth():
    """mock get_current_teacher 跳过 JWT 校验，固定返回 TEACHER_ID"""
    from app.main import app
    from app.core.security import get_current_teacher

    async def _fake():
        return TEACHER_ID

    app.dependency_overrides[get_current_teacher] = _fake
    yield
    app.dependency_overrides.pop(get_current_teacher, None)


# ═══════════════════════════════════════════════════════════════════════════════
#  1. 列目录 / 读 / 保存 / 删除
# ═══════════════════════════════════════════════════════════════════════════════


class TestListReadSaveDelete:

    @pytest.mark.asyncio
    async def test_list_empty(
        self, db_session, tmp_path, monkeypatch, override_get_db, mock_teacher_auth
    ):
        snap = await _create_snapshot(db_session, monkeypatch, tmp_path)
        async with await _client() as c:
            res = await c.get(_url(snap.id), headers=_auth())
        assert res.status_code == 200
        assert res.json()["data"]["items"] == []

    @pytest.mark.asyncio
    async def test_save_read_roundtrip(
        self, db_session, tmp_path, monkeypatch, override_get_db, mock_teacher_auth
    ):
        snap = await _create_snapshot(db_session, monkeypatch, tmp_path, "rw")

        async with await _client() as c:
            # 保存新文件
            save_res = await c.post(
                _url(snap.id, "/save"),
                json={"path": "hello.txt", "content": "world"},
                headers=_auth(),
            )
            assert save_res.status_code == 200

            # 读回
            read_res = await c.get(
                _url(snap.id, "/read"), params={"path": "hello.txt"}, headers=_auth()
            )
            assert read_res.status_code == 200
            assert read_res.json()["data"]["content"] == "world"

            # 列目录应包含该文件
            list_res = await c.get(_url(snap.id), headers=_auth())
            names = [i["name"] for i in list_res.json()["data"]["items"]]
            assert "hello.txt" in names

        # stats_updater 已被调用：file_count 应 > 0
        await db_session.refresh(snap)
        assert snap.file_count >= 1
        assert snap.total_size_bytes == len("world")

    @pytest.mark.asyncio
    async def test_delete_file(
        self, db_session, tmp_path, monkeypatch, override_get_db, mock_teacher_auth
    ):
        snap = await _create_snapshot(db_session, monkeypatch, tmp_path, "del")
        # 预置文件
        (Path(snap.storage_root) / "tmp.txt").write_text("x")

        async with await _client() as c:
            res = await c.delete(
                _url(snap.id, "/delete"), params={"path": "tmp.txt"}, headers=_auth()
            )
        assert res.status_code == 200
        assert res.json()["code"] == 0
        assert not (Path(snap.storage_root) / "tmp.txt").exists()

        await db_session.refresh(snap)
        assert snap.file_count == 0

    @pytest.mark.asyncio
    async def test_read_traversal_rejected(
        self, db_session, tmp_path, monkeypatch, override_get_db, mock_teacher_auth
    ):
        snap = await _create_snapshot(db_session, monkeypatch, tmp_path, "trv")
        async with await _client() as c:
            res = await c.get(
                _url(snap.id, "/read"), params={"path": "../../etc/passwd"}, headers=_auth()
            )
        assert res.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════════
#  2. 上传
# ═══════════════════════════════════════════════════════════════════════════════


class TestUpload:

    @pytest.mark.asyncio
    async def test_upload_file_root(
        self, db_session, tmp_path, monkeypatch, override_get_db, mock_teacher_auth
    ):
        snap = await _create_snapshot(db_session, monkeypatch, tmp_path, "upl")

        async with await _client() as c:
            res = await c.post(
                _url(snap.id, "/upload"),
                files={"file": ("a.sh", b"#!/bin/bash", "text/plain")},
                headers=_auth(),
            )
        assert res.status_code == 200
        body = res.json()["data"]
        assert body["file_count"] == 1
        assert body["total_size_bytes"] == len("#!/bin/bash")
        assert (Path(snap.storage_root) / "a.sh").exists()

    @pytest.mark.asyncio
    async def test_upload_traversal_in_target_dir_rejected(
        self, db_session, tmp_path, monkeypatch, override_get_db, mock_teacher_auth
    ):
        snap = await _create_snapshot(db_session, monkeypatch, tmp_path, "upl_trv")
        async with await _client() as c:
            res = await c.post(
                _url(snap.id, "/upload"),
                files={"file": ("a.sh", b"x", "text/plain")},
                data={"path": "../../evil"},
                headers=_auth(),
            )
        assert res.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════════
#  3. mkdir / rename
# ═══════════════════════════════════════════════════════════════════════════════


class TestMkdirRename:

    @pytest.mark.asyncio
    async def test_mkdir(
        self, db_session, tmp_path, monkeypatch, override_get_db, mock_teacher_auth
    ):
        snap = await _create_snapshot(db_session, monkeypatch, tmp_path, "mkd")

        async with await _client() as c:
            res = await c.post(
                _url(snap.id, "/mkdir"), json={"path": "sub/nested"}, headers=_auth()
            )
        assert res.status_code == 200
        assert (Path(snap.storage_root) / "sub" / "nested").is_dir()

    @pytest.mark.asyncio
    async def test_rename(
        self, db_session, tmp_path, monkeypatch, override_get_db, mock_teacher_auth
    ):
        snap = await _create_snapshot(db_session, monkeypatch, tmp_path, "rn")
        (Path(snap.storage_root) / "old.txt").write_text("x")

        async with await _client() as c:
            res = await c.post(
                _url(snap.id, "/rename"),
                json={"path": "old.txt", "new_name": "new.txt"},
                headers=_auth(),
            )
        assert res.status_code == 200
        assert (Path(snap.storage_root) / "new.txt").exists()
        assert not (Path(snap.storage_root) / "old.txt").exists()


# ═══════════════════════════════════════════════════════════════════════════════
#  4. move / copy
# ═══════════════════════════════════════════════════════════════════════════════


class TestMoveCopy:

    @pytest.mark.asyncio
    async def test_move(
        self, db_session, tmp_path, monkeypatch, override_get_db, mock_teacher_auth
    ):
        snap = await _create_snapshot(db_session, monkeypatch, tmp_path, "mv")
        (Path(snap.storage_root) / "src.txt").write_text("x")
        (Path(snap.storage_root) / "dst_dir").mkdir()

        async with await _client() as c:
            res = await c.post(
                _url(snap.id, "/move"),
                json={"source_paths": ["src.txt"], "target_dir": "dst_dir"},
                headers=_auth(),
            )
        assert res.status_code == 200
        assert (Path(snap.storage_root) / "dst_dir" / "src.txt").exists()
        assert not (Path(snap.storage_root) / "src.txt").exists()

    @pytest.mark.asyncio
    async def test_copy(
        self, db_session, tmp_path, monkeypatch, override_get_db, mock_teacher_auth
    ):
        snap = await _create_snapshot(db_session, monkeypatch, tmp_path, "cp")
        (Path(snap.storage_root) / "src.txt").write_text("x")
        (Path(snap.storage_root) / "dst_dir").mkdir()

        async with await _client() as c:
            res = await c.post(
                _url(snap.id, "/copy"),
                json={"source_paths": ["src.txt"], "target_dir": "dst_dir"},
                headers=_auth(),
            )
        assert res.status_code == 200
        assert (Path(snap.storage_root) / "dst_dir" / "src.txt").exists()
        # 源文件保留
        assert (Path(snap.storage_root) / "src.txt").exists()


# ═══════════════════════════════════════════════════════════════════════════════
#  5. extract / compress
# ═══════════════════════════════════════════════════════════════════════════════


class TestCompressExtract:

    @pytest.mark.asyncio
    async def test_compress_then_extract(
        self, db_session, tmp_path, monkeypatch, override_get_db, mock_teacher_auth
    ):
        snap = await _create_snapshot(db_session, monkeypatch, tmp_path, "zip")
        (Path(snap.storage_root) / "file1.txt").write_text("aaa")
        (Path(snap.storage_root) / "file2.txt").write_text("bbb")

        async with await _client() as c:
            # 压缩
            res = await c.post(
                _url(snap.id, "/compress"),
                json={
                    "paths": ["file1.txt", "file2.txt"],
                    "archive_name": "bundle.zip",
                    "format": "zip",
                },
                headers=_auth(),
            )
            assert res.status_code == 200
            assert (Path(snap.storage_root) / "bundle.zip").exists()

            # 解压到子目录
            res2 = await c.post(
                _url(snap.id, "/extract"),
                json={"path": "bundle.zip", "target_dir": "unzipped"},
                headers=_auth(),
            )
            assert res2.status_code == 200
            assert (Path(snap.storage_root) / "unzipped" / "file1.txt").exists()


# ═══════════════════════════════════════════════════════════════════════════════
#  6. download
# ═══════════════════════════════════════════════════════════════════════════════


class TestDownload:

    @pytest.mark.asyncio
    async def test_download_single_file(
        self, db_session, tmp_path, monkeypatch, override_get_db, mock_teacher_auth
    ):
        snap = await _create_snapshot(db_session, monkeypatch, tmp_path, "dl")
        (Path(snap.storage_root) / "report.txt").write_text("hello download")

        async with await _client() as c:
            res = await c.get(
                _url(snap.id, "/download"), params={"path": "report.txt"}, headers=_auth()
            )
        assert res.status_code == 200
        assert res.content == b"hello download"
        assert "attachment" in res.headers.get("content-disposition", "")

    @pytest.mark.asyncio
    async def test_download_file_with_non_ascii_name(
        self, db_session, tmp_path, monkeypatch, override_get_db, mock_teacher_auth
    ):
        """回归：中文文件名应走 RFC 5987 filename*= 编码，不抛 UnicodeEncodeError"""
        snap = await _create_snapshot(db_session, monkeypatch, tmp_path, "cjk")
        (Path(snap.storage_root) / "C方案.md").write_text("hello 中文", encoding="utf-8")

        async with await _client() as c:
            res = await c.get(
                _url(snap.id, "/download"), params={"path": "C方案.md"}, headers=_auth()
            )
        assert res.status_code == 200
        assert res.content.decode("utf-8") == "hello 中文"
        cd = res.headers.get("content-disposition", "")
        # 含非 ASCII 时应使用 filename*=UTF-8'' 形式
        assert "filename*=UTF-8''" in cd
        # URL 编码后的 "C方案.md"
        from urllib.parse import quote
        assert quote("C方案.md", safe="") in cd

    @pytest.mark.asyncio
    async def test_download_directory_as_zip(
        self, db_session, tmp_path, monkeypatch, override_get_db, mock_teacher_auth
    ):
        snap = await _create_snapshot(db_session, monkeypatch, tmp_path, "dlz")
        sub = Path(snap.storage_root) / "pack"
        sub.mkdir()
        (sub / "a.txt").write_text("1")
        (sub / "b.txt").write_text("22")

        async with await _client() as c:
            res = await c.get(
                _url(snap.id, "/download"), params={"path": "pack"}, headers=_auth()
            )
        assert res.status_code == 200
        # 返回 zip stream，验证可被 zipfile 解析
        zf = zipfile.ZipFile(io.BytesIO(res.content))
        names = zf.namelist()
        assert any("a.txt" in n for n in names)
        assert any("b.txt" in n for n in names)


# ═══════════════════════════════════════════════════════════════════════════════
#  7. 404 / 403 权限隔离
# ═══════════════════════════════════════════════════════════════════════════════


class TestAuthIsolation:

    @pytest.mark.asyncio
    async def test_not_found_snapshot(self, override_get_db, mock_teacher_auth):
        """id 不存在 → 404（由 resolver 抛出 HTTPException）"""
        async with await _client() as c:
            res = await c.get(_url(99999), headers=_auth())
        assert res.status_code == 404

    @pytest.mark.asyncio
    async def test_forbidden_other_teacher(
        self, db_session, tmp_path, monkeypatch, override_get_db
    ):
        """非所有者教师 → 403"""
        from app.main import app
        from app.core.security import get_current_teacher

        snap = await _create_snapshot(db_session, monkeypatch, tmp_path, "forb")

        async def _fake_other():
            return TEACHER_ID + 100  # 另一个老师

        app.dependency_overrides[get_current_teacher] = _fake_other
        try:
            async with await _client() as c:
                res = await c.get(_url(snap.id), headers=_auth())
            assert res.status_code == 403
        finally:
            app.dependency_overrides.pop(get_current_teacher, None)
