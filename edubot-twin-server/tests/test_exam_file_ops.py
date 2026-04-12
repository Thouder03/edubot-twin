"""
考试域文件操作与复制异常测试（第11期差距补全）

覆盖 SDD §7 中被原测试遗漏的场景：
1. snapshot_copier：源 bundle 不存在 → 抛出 SnapshotCopyError
2. snapshot_copier：shutil.copytree 磁盘 I/O 异常 → 清理目标目录 + 抛异常
3. BundleFileService：文件路径穿越攻击 → 抛 PathTraversalError
4. ExamEvalScript：上传入口文件后 validate_status 自动变更 valid
"""
from pathlib import Path

import pytest

from app.core.snapshot_copier import SnapshotCopyError, copy_snapshot
from app.crud import exam_eval_script as crud_eval_script
from app.services.bundle_file_service import BundleFileService, PathTraversalError


TEACHER_ID = 1


# ═══════════════════════════════════════════════════════════════════════════════
#  1. snapshot_copier 异常分支
# ═══════════════════════════════════════════════════════════════════════════════


class TestSnapshotCopierExceptions:

    def test_source_not_exists(self, tmp_path: Path):
        """源目录不存在 → 抛出 SnapshotCopyError，目标目录保持未创建"""
        source = tmp_path / "non_existent_source"
        target = tmp_path / "target"

        with pytest.raises(SnapshotCopyError) as exc_info:
            copy_snapshot(str(source), str(target))

        assert "源目录不存在" in str(exc_info.value)
        assert not target.exists()

    def test_source_is_file_not_dir(self, tmp_path: Path):
        """源路径是文件（非目录）→ 抛出 SnapshotCopyError"""
        source_file = tmp_path / "not_a_dir.txt"
        source_file.write_text("hello")
        target = tmp_path / "target"

        with pytest.raises(SnapshotCopyError) as exc_info:
            copy_snapshot(str(source_file), str(target))

        assert "不是目录" in str(exc_info.value)
        assert not target.exists()

    def test_copytree_io_error_cleans_up_target(self, tmp_path: Path, monkeypatch):
        """shutil.copytree 抛 I/O 异常 → 目标目录被清理 + 抛 SnapshotCopyError"""
        source = tmp_path / "src"
        source.mkdir()
        (source / "file.txt").write_text("x")
        target = tmp_path / "tgt"

        import shutil

        original_copytree = shutil.copytree

        def _mock_copytree(src, dst, *args, **kwargs):
            # 模拟 copytree 创建了部分目录后失败
            Path(dst).mkdir(parents=True, exist_ok=True)
            (Path(dst) / "partial.txt").write_text("partial")
            raise OSError("Disk full (simulated)")

        monkeypatch.setattr(shutil, "copytree", _mock_copytree)

        with pytest.raises(SnapshotCopyError) as exc_info:
            copy_snapshot(str(source), str(target))

        assert "Disk full" in str(exc_info.value)
        # 关键断言：不完整目标目录已被清理
        assert not target.exists()

        # 恢复以避免污染其它测试
        monkeypatch.setattr(shutil, "copytree", original_copytree)

    def test_copy_success_returns_stats(self, tmp_path: Path):
        """正常路径：复制 2 个文件 → 返回 (2, size_sum)"""
        source = tmp_path / "src"
        source.mkdir()
        (source / "a.txt").write_text("aaa")
        (source / "b.txt").write_text("bbbb")
        target = tmp_path / "tgt"

        count, size = copy_snapshot(str(source), str(target))

        assert count == 2
        assert size == len("aaa") + len("bbbb")
        assert target.exists()
        assert (target / "a.txt").read_text() == "aaa"


# ═══════════════════════════════════════════════════════════════════════════════
#  2. BundleFileService 路径穿越安全测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestBundleFilePathTraversal:
    """验证 BundleFileService._safe_path 对所有常见路径穿越攻击的拦截"""

    @pytest.fixture
    def svc(self, tmp_path: Path) -> BundleFileService:
        root = tmp_path / "bundle_root"
        root.mkdir()
        (root / "legit.txt").write_text("legit")
        return BundleFileService(storage_root=str(root))

    @pytest.mark.parametrize(
        "bad_path",
        [
            "../etc/passwd",
            "../../../../etc/passwd",
            "subdir/../../etc/passwd",
            "/etc/passwd",
            "/absolute/path",
        ],
    )
    def test_read_rejects_traversal(self, svc: BundleFileService, bad_path: str):
        with pytest.raises(PathTraversalError):
            svc.read_file(bad_path)

    @pytest.mark.parametrize(
        "bad_path",
        [
            "../evil.txt",
            "../../evil.sh",
            "/tmp/evil",
        ],
    )
    def test_save_rejects_traversal(self, svc: BundleFileService, bad_path: str):
        with pytest.raises(PathTraversalError):
            svc.save_file(bad_path, "pwned")

    @pytest.mark.parametrize(
        "bad_path",
        [
            "../legit.txt",
            "../../legit.txt",
            "/legit.txt",
        ],
    )
    def test_delete_rejects_traversal(self, svc: BundleFileService, bad_path: str):
        with pytest.raises(PathTraversalError):
            svc.delete_file(bad_path)

    @pytest.mark.parametrize(
        "bad_dir",
        [
            "../evil",
            "../../outside",
            "/tmp/absolute",
        ],
    )
    def test_upload_rejects_traversal_in_target_dir(
        self, svc: BundleFileService, bad_dir: str
    ):
        """上传时通过 target_dir 参数尝试路径穿越 → 必须被拦截"""
        with pytest.raises(PathTraversalError):
            svc.save_uploaded_file("legit.sh", b"data", target_dir=bad_dir)

    def test_upload_sanitizes_traversal_in_filename(
        self, svc: BundleFileService, tmp_path: Path
    ):
        """上传时 filename 中的路径字符应被 Path().name 剥离，落盘到 storage_root 根目录"""
        target = svc.save_uploaded_file("../../evil.sh", b"data")
        # 必须落盘到 storage_root 根目录下的纯 basename
        assert target.name == "evil.sh"
        assert target.parent == svc.storage_root
        # 原假冒的父目录不存在
        assert not (svc.storage_root.parent / "evil.sh").exists()

    def test_legit_path_ok(self, svc: BundleFileService):
        """校验合法路径不受误杀"""
        content, _ = svc.read_file("legit.txt")
        assert content == "legit"

        # 允许写入新子目录
        svc.save_file("subdir/new.py", "print(1)")
        svc.read_file("subdir/new.py")


# ═══════════════════════════════════════════════════════════════════════════════
#  3. ExamEvalScript：validate_status 文件系统级测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestEvalScriptValidateStatus:
    """验证 update_eval_script_stats 根据文件系统上 entry_point 的存在性更新状态"""

    @pytest.mark.asyncio
    async def test_pending_when_empty(self, db_session, tmp_path: Path, monkeypatch):
        """空脚本包 → validate_status = pending"""
        monkeypatch.setattr(
            crud_eval_script, "EXAM_EVAL_SCRIPTS_BASE_DIR", tmp_path / "eval_scripts"
        )
        script = await crud_eval_script.create_eval_script(
            db_session,
            name="空脚本",
            entry_point="evaluate.sh",
            created_by=TEACHER_ID,
        )
        assert script.validate_status.value == "pending"
        assert script.file_count == 0

    @pytest.mark.asyncio
    async def test_becomes_valid_after_writing_entry_file(
        self, db_session, tmp_path: Path, monkeypatch
    ):
        """在 storage_root 落盘 entry_point 后，update_stats 会把状态切为 valid"""
        monkeypatch.setattr(
            crud_eval_script, "EXAM_EVAL_SCRIPTS_BASE_DIR", tmp_path / "eval_scripts"
        )
        script = await crud_eval_script.create_eval_script(
            db_session,
            name="自动校验脚本",
            entry_point="evaluate.sh",
            created_by=TEACHER_ID,
        )

        # 在 storage_root 中落盘 entry_point
        entry_file = Path(script.storage_root) / "evaluate.sh"
        entry_file.write_text("#!/bin/bash\necho ok\n")

        # 调用 update_stats 触发自动校验（模拟上传/保存/删除流程）
        script = await crud_eval_script.update_eval_script_stats(
            db_session, script=script, file_count=1, total_size_bytes=entry_file.stat().st_size
        )
        assert script.validate_status.value == "valid"
        assert script.file_count == 1

    @pytest.mark.asyncio
    async def test_becomes_invalid_when_entry_missing_but_has_files(
        self, db_session, tmp_path: Path, monkeypatch
    ):
        """上传了文件但没有 entry_point → invalid"""
        monkeypatch.setattr(
            crud_eval_script, "EXAM_EVAL_SCRIPTS_BASE_DIR", tmp_path / "eval_scripts"
        )
        script = await crud_eval_script.create_eval_script(
            db_session,
            name="错上传",
            entry_point="evaluate.sh",
            created_by=TEACHER_ID,
        )

        # 只落盘 helper.sh，不落盘 evaluate.sh
        (Path(script.storage_root) / "helper.sh").write_text("hi")

        script = await crud_eval_script.update_eval_script_stats(
            db_session, script=script, file_count=1, total_size_bytes=2
        )
        assert script.validate_status.value == "invalid"

    @pytest.mark.asyncio
    async def test_valid_to_invalid_after_entry_deletion(
        self, db_session, tmp_path: Path, monkeypatch
    ):
        """从 valid → invalid：删除 entry_point 后再调用 update_stats"""
        monkeypatch.setattr(
            crud_eval_script, "EXAM_EVAL_SCRIPTS_BASE_DIR", tmp_path / "eval_scripts"
        )
        script = await crud_eval_script.create_eval_script(
            db_session,
            name="可删除脚本",
            entry_point="evaluate.sh",
            created_by=TEACHER_ID,
        )
        entry = Path(script.storage_root) / "evaluate.sh"
        entry.write_text("ok")

        script = await crud_eval_script.update_eval_script_stats(
            db_session, script=script, file_count=1, total_size_bytes=2
        )
        assert script.validate_status.value == "valid"

        # 删除入口文件，模拟 delete_file 后端处理
        entry.unlink()
        (Path(script.storage_root) / "other.txt").write_text("x")

        script = await crud_eval_script.update_eval_script_stats(
            db_session, script=script, file_count=1, total_size_bytes=1
        )
        assert script.validate_status.value == "invalid"

    @pytest.mark.asyncio
    async def test_entry_point_rename_triggers_revalidate(
        self, db_session, tmp_path: Path, monkeypatch
    ):
        """patch entry_point 指向一个已存在的文件 → 变 valid"""
        monkeypatch.setattr(
            crud_eval_script, "EXAM_EVAL_SCRIPTS_BASE_DIR", tmp_path / "eval_scripts"
        )
        script = await crud_eval_script.create_eval_script(
            db_session,
            name="重命名 entry",
            entry_point="evaluate.sh",
            created_by=TEACHER_ID,
        )
        # 文件名是 run.sh，但 entry_point 默认 evaluate.sh → invalid
        (Path(script.storage_root) / "run.sh").write_text("ok")
        script = await crud_eval_script.update_eval_script_stats(
            db_session, script=script, file_count=1, total_size_bytes=2
        )
        assert script.validate_status.value == "invalid"

        # 将 entry_point 改为 run.sh → 应自动变 valid
        script = await crud_eval_script.update_eval_script(
            db_session, script=script, entry_point="run.sh"
        )
        assert script.validate_status.value == "valid"
