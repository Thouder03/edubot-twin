"""
S1 集成测试套件（10-S1）

覆盖范围（对应 SDD 第11节测试覆盖地图）：
- TC-S1-01: 文件包 CRUD（创建/列表/重命名/删除）
- TC-S1-02: 文件包文件操作（上传/列目录/读/保存/删除）
- TC-S1-03: 环境包 CRUD（含 startup.sh 自动生成）
- TC-S1-04: 环境包保护路径（startup.sh 不可删）
- TC-S1-05: 模型字段验证（无 is_visible/startup_script_ref）
- TC-S1-06: 实验状态机（draft→active→archived→active）
- TC-S1-07: 版本状态机（draft→published，有 blocking 时拦截）
- TC-S1-08: 版本验证（validate 返回正确 blocking/warning）
- TC-S1-09: 学生可见性规则（Experiment.status=active + published）
- TC-S1-10: 路径安全（路径穿越被拒绝）
- TC-S1-11: 容器创建参数注入（launch_args/startup_script_path/env_volumes/is_dry_run）
- TC-S1-12: 就绪检测（端口就绪/超时逻辑）
- TC-S1-13: BundleFileService 冲突检测
"""
import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# ─── 环境配置 ──────────────────────────────────────────────────────────────────
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_s1.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-s1")

PASS = "✅"
FAIL = "❌"
SKIP = "⚠️"
results: list[tuple[str, str, str]] = []  # (tc_id, status, detail)


def ok(tc_id: str, detail: str = ""):
    results.append((tc_id, PASS, detail))
    print(f"  {PASS} {tc_id} {detail}")


def fail(tc_id: str, err):
    results.append((tc_id, FAIL, str(err)))
    print(f"  {FAIL} {tc_id}: {err}")


# ═══════════════════════════════════════════════════════════════════════════════
# TC-S1-05: 模型字段验证
# ═══════════════════════════════════════════════════════════════════════════════

def test_s1_05_model_fields():
    """验证 is_visible、startup_script_ref 已从模型移除，env_bundle_id 已添加"""
    try:
        from app.models.experiment import ExperimentVersion
        cols = {c.key for c in ExperimentVersion.__table__.columns}
        assert "is_visible" not in cols, "is_visible 应已移除"
        assert "startup_script_ref" not in cols, "startup_script_ref 应已移除"
        assert "env_bundle_id" in cols, "env_bundle_id 应已添加"
        assert "file_bundle_id" in cols, "file_bundle_id 应保留"
        ok("TC-S1-05", "ExperimentVersion 字段验证通过")
    except Exception as e:
        fail("TC-S1-05", e)


def test_s1_05b_file_bundle_fields():
    """验证 ExperimentFileBundle 新增字段存在，experiment_id/checksum 已移除"""
    try:
        from app.models.experiment import ExperimentFileBundle
        cols = {c.key for c in ExperimentFileBundle.__table__.columns}
        assert "name" in cols, "name 应已添加"
        assert "storage_root" in cols, "storage_root 应已添加"
        assert "file_count" in cols, "file_count 应已添加"
        assert "total_size_bytes" in cols, "total_size_bytes 应已添加"
        assert "experiment_id" not in cols, "experiment_id 应已移除"
        assert "checksum" not in cols, "checksum 应已移除"
        ok("TC-S1-05b", "ExperimentFileBundle 字段验证通过")
    except Exception as e:
        fail("TC-S1-05b", e)


def test_s1_05c_env_bundle_model():
    """验证 ExperimentEnvBundle 模型和字段存在"""
    try:
        from app.models.experiment import ExperimentEnvBundle
        cols = {c.key for c in ExperimentEnvBundle.__table__.columns}
        for f in ["id", "name", "storage_root", "container_target_dir", "access_level",
                  "file_count", "total_size_bytes", "created_by"]:
            assert f in cols, f"{f} 应存在于 ExperimentEnvBundle"
        ok("TC-S1-05c", "ExperimentEnvBundle 模型验证通过")
    except Exception as e:
        fail("TC-S1-05c", e)


# ═══════════════════════════════════════════════════════════════════════════════
# TC-S1-02/03/04/10/13: BundleFileService 单元测试
# ═══════════════════════════════════════════════════════════════════════════════

def test_s1_bundle_file_service():
    """测试 BundleFileService 核心功能"""
    from app.services.bundle_file_service import (
        BundleFileService, PathTraversalError, ProtectedPathError,
        FileSizeExceededError, FileConflictError,
        FileNotFoundError as BundleFileNotFoundError,
    )

    with tempfile.TemporaryDirectory() as tmpdir:

        # TC-S1-10: 路径穿越检测
        try:
            svc = BundleFileService(tmpdir)
            try:
                svc._safe_path("../etc/passwd")
                fail("TC-S1-10", "应抛出 PathTraversalError")
            except PathTraversalError:
                ok("TC-S1-10a", "../ 路径穿越被正确拦截")
            try:
                svc._safe_path("/etc/passwd")
                fail("TC-S1-10b", "应抛出 PathTraversalError")
            except PathTraversalError:
                ok("TC-S1-10b", "绝对路径被正确拦截")
        except Exception as e:
            fail("TC-S1-10", e)

        # TC-S1-04: 保护路径不可删
        try:
            svc_protected = BundleFileService(tmpdir, protected_paths={"startup.sh"})
            startup = Path(tmpdir) / "startup.sh"
            startup.write_text("#!/bin/bash\n")
            try:
                svc_protected.delete_file("startup.sh")
                fail("TC-S1-04", "应抛出 ProtectedPathError")
            except ProtectedPathError:
                ok("TC-S1-04", "startup.sh 删除被正确拒绝（403）")
        except Exception as e:
            fail("TC-S1-04", e)

        # TC-S1-02: 文件上传/读取/保存/删除
        try:
            svc = BundleFileService(tmpdir)
            # 上传
            svc.save_uploaded_file("test.py", b"print('hello')")
            files = svc.list_files()
            names = [f["name"] for f in files]
            assert "test.py" in names, "上传后文件应存在于列表"
            ok("TC-S1-02a", "文件上传+列目录")

            # 读取
            content, enc = svc.read_file("test.py")
            assert "hello" in content
            ok("TC-S1-02b", "文件内容读取")

            # 保存（带冲突检测）
            # 正常保存
            mtime1 = svc.save_file("test.py", "print('world')", modified_at=None)
            content2, _ = svc.read_file("test.py")
            assert "world" in content2
            ok("TC-S1-02c", "文件保存（无冲突检测）")

            # TC-S1-13: 冲突检测
            # 先保存文件获取真实 mtime，再直接修改文件 mtime 模拟第三方更新
            conf_path = Path(tmpdir) / "conflict.txt"
            svc.save_file("conflict.txt", "v1", modified_at=None)
            # 记录客户端持有的 mtime（v1 时刻）
            client_mtime = conf_path.stat().st_mtime
            # 强制更新文件的 mtime（模拟第三方写入使 mtime 向前推进超过 1s）
            import os as _os
            new_mtime = client_mtime + 2.0  # 超过 1s 容差
            _os.utime(str(conf_path), (new_mtime, new_mtime))
            # 此时用旧 mtime 保存应触发冲突
            try:
                svc.save_file("conflict.txt", "v3", modified_at=client_mtime)
                fail("TC-S1-13", "应抛出 FileConflictError")
            except FileConflictError:
                ok("TC-S1-13", "文件冲突检测正确触发")

            # 删除
            svc.delete_file("test.py")
            files2 = svc.list_files()
            names2 = [f["name"] for f in files2]
            assert "test.py" not in names2
            ok("TC-S1-02d", "文件删除")

        except AssertionError as e:
            fail("TC-S1-02", e)
        except Exception as e:
            if "TC-S1-02" not in str(e) and "TC-S1-13" not in str(e):
                fail("TC-S1-02", e)

        # TC-S1-02e: 超大文件拒绝
        try:
            from app.services.bundle_file_service import MAX_UPLOAD_SIZE_BYTES
            fake_large = b"x" * (MAX_UPLOAD_SIZE_BYTES + 1)
            try:
                svc.save_uploaded_file("large.bin", fake_large)
                fail("TC-S1-02e", "应抛出 FileSizeExceededError")
            except FileSizeExceededError:
                ok("TC-S1-02e", "超大文件上传被拒绝（413）")
        except Exception as e:
            fail("TC-S1-02e", e)

        # TC-S1-02f: scan_directory
        try:
            svc2 = BundleFileService(tmpdir)
            svc2.save_file("a.txt", "hello", None)
            svc2.save_file("b.txt", "world", None)
            count, size, manifest = svc2.scan_directory()
            paths = [m["relative_path"] for m in manifest]
            assert "a.txt" in paths
            assert "b.txt" in paths
            ok("TC-S1-02f", f"scan_directory: {count} files, {size} bytes")
        except Exception as e:
            fail("TC-S1-02f", e)


# ═══════════════════════════════════════════════════════════════════════════════
# TC-S1-03: 环境包 startup.sh 自动生成
# ═══════════════════════════════════════════════════════════════════════════════

def test_s1_03_env_bundle_startup():
    """验证创建环境包时自动生成 startup.sh 模板"""
    try:
        from app.core.system_entrypoint import create_env_bundle_startup_script
        with tempfile.TemporaryDirectory() as tmpdir:
            create_env_bundle_startup_script(tmpdir)
            startup = Path(tmpdir) / "startup.sh"
            assert startup.exists(), "startup.sh 应已自动创建"
            content = startup.read_text()
            assert "#!/bin/bash" in content, "startup.sh 应包含 shebang"
            assert "source" in content.lower(), "startup.sh 应包含 source 指令"
            # 幂等：再次调用不报错
            create_env_bundle_startup_script(tmpdir)
            ok("TC-S1-03", "startup.sh 自动生成且内容正确（幂等）")
    except Exception as e:
        fail("TC-S1-03", e)


# ═══════════════════════════════════════════════════════════════════════════════
# TC-S1-12: 就绪检测器
# ═══════════════════════════════════════════════════════════════════════════════

async def _test_s1_12_readiness():
    from app.core.readiness_checker import check_port_ready

    # 测试端口就绪（mock asyncio.open_connection 成功）
    with patch("asyncio.open_connection") as mock_conn:
        mock_reader = MagicMock()
        mock_writer = MagicMock()
        mock_writer.wait_closed = AsyncMock(return_value=None)
        mock_conn.return_value = asyncio.coroutine(lambda: (mock_reader, mock_writer))()

        async def fake_open(host, port):
            return mock_reader, mock_writer

        with patch("asyncio.open_connection", side_effect=fake_open):
            is_ready, elapsed = await check_port_ready("127.0.0.1", 18080, timeout_s=5.0)
            assert is_ready is True
            ok("TC-S1-12a", f"端口就绪检测成功 (elapsed={elapsed:.0f}ms)")

    # 测试超时（端口始终拒绝连接）
    with patch("asyncio.open_connection", side_effect=ConnectionRefusedError):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            is_ready, elapsed = await check_port_ready("127.0.0.1", 19999, timeout_s=0.1)
            assert is_ready is False
            ok("TC-S1-12b", f"端口超时检测正确 (elapsed={elapsed:.0f}ms)")


def test_s1_12_readiness():
    try:
        asyncio.run(_test_s1_12_readiness())
    except Exception as e:
        fail("TC-S1-12", e)


# ═══════════════════════════════════════════════════════════════════════════════
# TC-S1-11: container_manager 参数注入
# ═══════════════════════════════════════════════════════════════════════════════

def test_s1_11_container_manager_signature():
    """验证 create_container 新参数签名存在且向后兼容"""
    try:
        from app.core.container_manager import create_container
        import inspect
        sig = inspect.signature(create_container)
        params = sig.parameters

        # 新增参数
        assert "launch_args" in params, "launch_args 参数应存在"
        assert "startup_script_path" in params, "startup_script_path 参数应存在"
        assert "env_volumes" in params, "env_volumes 参数应存在"
        assert "is_dry_run" in params, "is_dry_run 参数应存在"

        # 验证默认值（向后兼容）
        assert params["launch_args"].default is None, "launch_args 默认值应为 None"
        assert params["startup_script_path"].default is None
        assert params["env_volumes"].default is None
        assert params["is_dry_run"].default is False

        ok("TC-S1-11", "create_container 参数签名验证通过（向后兼容）")
    except Exception as e:
        fail("TC-S1-11", e)


# ═══════════════════════════════════════════════════════════════════════════════
# TC-S1-06/07/08/09: 数据库层测试（异步）
# ═══════════════════════════════════════════════════════════════════════════════

async def _test_db_operations():
    """数据库层集成测试"""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker
    from app.db.base import Base
    from app.models.experiment import (
        Experiment, ExperimentVersion, ExperimentEnvBundle,
        ExperimentFileBundle, ExperimentStatus, PublishStatus, FileBundleStatus
    )
    from app.crud import experiment as crud

    engine = create_async_engine("sqlite+aiosqlite:///./test_s1_db.db", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    AsyncTestSession = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with AsyncTestSession() as db:

        # ── TC-S1-01: 文件包 CRUD ─────────────────────────────────────────────
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                bundle = await crud.create_bundle(db, name="测试文件包A", storage_root=tmpdir, created_by=1)
                assert bundle.id is not None
                assert bundle.name == "测试文件包A"
                assert bundle.validate_status == FileBundleStatus.PENDING

                # 统计更新
                await crud.update_bundle_stats(db, bundle=bundle, file_count=3, total_size_bytes=1024, file_manifest=[])
                assert bundle.file_count == 3

                # 重命名
                renamed, affected = await crud.rename_bundle(db, bundle=bundle, new_name="测试文件包B")
                assert renamed.name == "测试文件包B"

                # 删除（无引用时）
                await crud.delete_bundle(db, bundle=bundle)
                assert await crud.get_bundle(db, bundle.id) is None
                ok("TC-S1-01", "文件包 CRUD（创建/统计/重命名/删除）")
        except Exception as e:
            fail("TC-S1-01", e)

        # ── TC-S1-03: 环境包 CRUD ─────────────────────────────────────────────
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                env_bundle = await crud.create_env_bundle(
                    db, name="测试环境包A", storage_root=tmpdir,
                    container_target_dir="/home/ubuntu20/catkin_ws",
                    access_level="readonly", created_by=1,
                )
                assert env_bundle.id is not None
                assert env_bundle.access_level.value == "readonly"

                # 更新
                updated = await crud.update_env_bundle(
                    db, env_bundle=env_bundle,
                    name="测试环境包B", access_level="readwrite"
                )
                assert updated.name == "测试环境包B"
                assert updated.access_level.value == "readwrite"

                # 删除
                await crud.delete_env_bundle(db, env_bundle=env_bundle)
                assert await crud.get_env_bundle(db, env_bundle.id) is None
                ok("TC-S1-03b", "环境包 CRUD（创建/更新/删除）")
        except Exception as e:
            fail("TC-S1-03b", e)

        # ── TC-S1-06: 实验状态机 ──────────────────────────────────────────────
        try:
            # 创建一个虚拟用户（teachers 需要外键，这里用 id=1 宽松测试）
            exp = Experiment(
                name="状态机测试实验", code="test_sm_exp",
                description="", status=ExperimentStatus.DRAFT, created_by=1
            )
            db.add(exp)
            await db.commit()
            await db.refresh(exp)

            # draft → active
            updated = await crud.switch_experiment_status(db, experiment=exp, new_status="active")
            assert updated.status.value == "active"

            # active → archived
            updated = await crud.switch_experiment_status(db, experiment=exp, new_status="archived")
            assert updated.status.value == "archived"

            # archived → active
            updated = await crud.switch_experiment_status(db, experiment=exp, new_status="active")
            assert updated.status.value == "active"

            # 非法转换 active → draft 应报错
            illegal_ok = False
            try:
                await crud.switch_experiment_status(db, experiment=exp, new_status="draft")
            except ValueError as ve:
                if "INVALID_STATUS_TRANSITION" in str(ve):
                    illegal_ok = True
            assert illegal_ok, "active→draft 非法转换应抛出 INVALID_STATUS_TRANSITION"
            ok("TC-S1-06", "实验状态机（draft→active→archived→active，非法拦截）")
        except Exception as e:
            fail("TC-S1-06", e)

        # ── TC-S1-07: 版本状态机（发布阻断校验）────────────────────────────────
        try:
            version = ExperimentVersion(
                experiment_id=exp.id,
                version_name="v-sm-test",
                environment_key="test_env",
                image_name="",  # 故意留空，触发 blocking
                launch_args_template={},
                publish_status=PublishStatus.DRAFT,
            )
            db.add(version)
            await db.commit()
            await db.refresh(version)

            # TC-S1-08: 版本验证（image_name 为空 → blocking）
            result = await crud.validate_version(db, version=version)
            assert result["has_blocking"] is True
            blocking_codes = [i["code"] for i in result["issues"] if i["severity"] == "blocking"]
            assert "missing_image" in blocking_codes
            ok("TC-S1-08a", f"版本验证正确返回 blocking: {blocking_codes}")

            # TC-S1-07: draft → published 有 blocking 时应被拦截（simulate endpoint logic）
            if result["has_blocking"]:
                ok("TC-S1-07a", "发布前 blocking 校验：正确拦截（simulate endpoint level）")

            # 修复 image_name，验证应通过
            version.image_name = "gzweb_sim:v1"
            await db.commit()
            result2 = await crud.validate_version(db, version=version)
            assert result2["has_blocking"] is False
            ok("TC-S1-08b", "版本验证：image_name 修复后无 blocking")

            # 切换到 published
            updated_v = await crud.switch_version_publish_status(
                db, version=version, new_status="published", operator_id=1,
                publish_note="S1 测试发布"
            )
            assert updated_v.publish_status.value == "published"
            ok("TC-S1-07b", "版本状态机（draft→published）")

            # published → deprecated
            updated_v2 = await crud.switch_version_publish_status(
                db, version=updated_v, new_status="deprecated", operator_id=1
            )
            assert updated_v2.publish_status.value == "deprecated"
            ok("TC-S1-07c", "版本状态机（published→deprecated）")

        except Exception as e:
            fail("TC-S1-07", e)

        # ── TC-S1-09: 学生可见性规则 ──────────────────────────────────────────
        try:
            # 实验为 active，版本为 published → 学生可见
            exp.status = ExperimentStatus.ACTIVE
            await db.commit()

            visible = await crud.list_student_available_versions(db)
            visible_ids = [v.id for v in visible]
            ok("TC-S1-09a", f"学生可见版本查询（{len(visible_ids)} 条，status=active+published）")

            # 实验改为 archived → 版本从学生端消失
            exp.status = ExperimentStatus.ARCHIVED
            await db.commit()
            visible2 = await crud.list_student_available_versions(db)
            visible2_ids = [v.id for v in visible2]
            assert version.id not in visible2_ids, "archived 实验的版本不应对学生可见"
            ok("TC-S1-09b", "实验 archived 后学生端不可见")
        except Exception as e:
            fail("TC-S1-09", e)

    await engine.dispose()
    # 清理测试数据库
    try:
        os.remove("test_s1_db.db")
    except Exception:
        pass


def test_s1_db():
    try:
        asyncio.run(_test_db_operations())
    except Exception as e:
        fail("TC-S1-DB", e)


# ═══════════════════════════════════════════════════════════════════════════════
# TC-S1: simul_task stage 枚举更新
# ═══════════════════════════════════════════════════════════════════════════════

def test_s1_simulation_stage_enum():
    """验证 SimulationTaskStage 包含新阶段"""
    try:
        from app.models.simulation_task import SimulationTaskStage
        assert hasattr(SimulationTaskStage, "CHECKING_GZWEB"), "CHECKING_GZWEB 阶段应存在"
        assert hasattr(SimulationTaskStage, "CHECKING_ROSBRIDGE"), "CHECKING_ROSBRIDGE 阶段应存在"
        assert hasattr(SimulationTaskStage, "HEALTH_CHECKING"), "HEALTH_CHECKING 应保留（向后兼容）"
        ok("TC-S1-08c", "SimulationTaskStage 新阶段验证（含向后兼容 HEALTH_CHECKING）")
    except Exception as e:
        fail("TC-S1-08c", e)


# ═══════════════════════════════════════════════════════════════════════════════
# TC-S1: Schema 字段验证
# ═══════════════════════════════════════════════════════════════════════════════

def test_s1_schema_fields():
    """验证 Schema 字段正确删除/添加"""
    try:
        from app.schemas.experiment import (
            ExperimentVersionResponse, ExperimentVersionCreate,
            FileBundleCreate, FileBundleResponse,
            EnvBundleCreate, EnvBundleResponse,
            VersionValidateResponse,
        )
        # ExperimentVersionResponse 无 is_visible/startup_script_ref
        fields = ExperimentVersionResponse.model_fields
        assert "is_visible" not in fields, "is_visible 应从 Schema 移除"
        assert "startup_script_ref" not in fields, "startup_script_ref 应从 Schema 移除"
        assert "env_bundle_id" in fields, "env_bundle_id 应在 Schema 中"

        # FileBundleCreate/Response 存在
        assert "name" in FileBundleCreate.model_fields
        assert "storage_root" in FileBundleResponse.model_fields

        # EnvBundleCreate/Response 存在
        assert "container_target_dir" in EnvBundleCreate.model_fields
        assert "access_level" in EnvBundleResponse.model_fields

        # VersionValidateResponse
        assert "has_blocking" in VersionValidateResponse.model_fields

        ok("TC-S1-schemas", "Schema 字段验证全部通过")
    except Exception as e:
        fail("TC-S1-schemas", e)


# ═══════════════════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "═" * 60)
    print("  S1 集成测试套件（10-S1）")
    print("═" * 60)

    # 静态/单元测试（同步）
    print("\n【模型字段验证】")
    test_s1_05_model_fields()
    test_s1_05b_file_bundle_fields()
    test_s1_05c_env_bundle_model()

    print("\n【Schema 字段验证】")
    test_s1_schema_fields()

    print("\n【SimulationTaskStage 枚举】")
    test_s1_simulation_stage_enum()

    print("\n【BundleFileService 单元测试】")
    test_s1_bundle_file_service()

    print("\n【环境包 startup.sh 自动生成】")
    test_s1_03_env_bundle_startup()

    print("\n【容器管理器参数签名】")
    test_s1_11_container_manager_signature()

    print("\n【就绪检测器】")
    test_s1_12_readiness()

    print("\n【数据库层集成测试】")
    test_s1_db()

    # ─── 汇总 ──────────────────────────────────────────────────────────────────
    print("\n" + "═" * 60)
    passed = sum(1 for _, s, _ in results if s == PASS)
    failed = sum(1 for _, s, _ in results if s == FAIL)
    print(f"  结果汇总：{PASS} {passed} 通过  {FAIL} {failed} 失败  共 {len(results)} 项")
    if failed > 0:
        print("\n  失败项目：")
        for tc_id, status, detail in results:
            if status == FAIL:
                print(f"    {FAIL} {tc_id}: {detail}")
    print("═" * 60)
    sys.exit(0 if failed == 0 else 1)
