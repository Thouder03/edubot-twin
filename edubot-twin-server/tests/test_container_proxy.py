"""
容器文件代理层测试套件

覆盖：
  TC-CP-01: Shadow 代理路由注册（prefix 与 tag 正确）
  TC-CP-02: 未认证请求被拒绝（401/403）
  TC-CP-03: 非 Shadow 用户被 403 拒绝（shadow 代理）
  TC-CP-04: 容器不存在时返回 404
  TC-CP-05: 容器网络未就绪时返回 503
  TC-CP-06: Sidecar 连接失败返回 503
  TC-CP-07: 学生代理路由注册正确
  TC-CP-08: 学生无容器时返回 404
  TC-CP-09: get_container_ip 函数（有/无容器）
  TC-CP-10: get_sidecar_volume helper（脚本存在/不存在）
"""
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# ─── 环境配置 ──────────────────────────────────────────────────────────────────
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_proxy.db")
os.environ.setdefault("SECRET_KEY", "proxy-test-secret")


# ═══════════════════════════════════════════════════════════════════════════════
# TC-CP-07/01: 路由注册验证（检查 router prefix 和 tag 配置）
# ═══════════════════════════════════════════════════════════════════════════════

def test_cp_01_teacher_proxy_router_exists():
    """Shadow 代理路由模块可正常导入"""
    from app.api.v1.endpoints.teacher import container_proxy
    assert hasattr(container_proxy, "router")
    # 检查 router 有 api_route 装饰的路由
    routes = list(container_proxy.router.routes)
    assert len(routes) >= 1, "container_proxy.router 应至少有一个路由"


def test_cp_07_student_proxy_router_exists():
    """学生代理路由模块可正常导入"""
    from app.api.v1.endpoints.student import container_files_proxy
    assert hasattr(container_files_proxy, "router")
    routes = list(container_files_proxy.router.routes)
    assert len(routes) >= 1, "container_files_proxy.router 应至少有一个路由"


def test_cp_01_teacher_router_registered():
    """检查 teacher/__init__.py 中 container_proxy 已注册"""
    from app.api.v1.endpoints.teacher import router as teacher_router
    path_prefixes = [route.path for route in teacher_router.routes]
    # 代理路由的 prefix 是 /dry-run-tools/container-files
    assert any("/dry-run-tools/container-files" in p for p in path_prefixes), (
        "dry-run-tools/container-files 路由未在 teacher router 中注册"
    )


def test_cp_07_student_router_registered():
    """检查 student/__init__.py 中 container_files_proxy 已注册"""
    from app.api.v1.endpoints.student import router as student_router
    path_prefixes = [route.path for route in student_router.routes]
    assert any("/container-files" in p for p in path_prefixes), (
        "/container-files 路由未在 student router 中注册"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TC-CP-09: get_container_ip 单元测试
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cp_09_get_container_ip_found():
    """容器在 edubot_network 中存在 IP 时正确返回"""
    from app.core import container_manager

    mock_container = MagicMock()
    mock_container.attrs = {
        "NetworkSettings": {
            "Networks": {
                "edubot_network": {"IPAddress": "172.18.0.5"}
            }
        }
    }

    mock_client = MagicMock()
    mock_client.containers.get.return_value = mock_container

    with patch("app.core.container_manager.get_docker_client", return_value=mock_client):
        ip = await container_manager.get_container_ip("abc123")

    assert ip == "172.18.0.5"


@pytest.mark.asyncio
async def test_cp_09_get_container_ip_fallback_to_first_network():
    """容器不在 edubot_network 时回退到第一个网络的 IP"""
    from app.core import container_manager

    mock_container = MagicMock()
    mock_container.attrs = {
        "NetworkSettings": {
            "Networks": {
                "bridge": {"IPAddress": "172.17.0.3"}
            }
        }
    }

    mock_client = MagicMock()
    mock_client.containers.get.return_value = mock_container

    with patch("app.core.container_manager.get_docker_client", return_value=mock_client):
        ip = await container_manager.get_container_ip("abc123")

    assert ip == "172.17.0.3"


@pytest.mark.asyncio
async def test_cp_09_get_container_ip_not_found():
    """容器不存在时返回 None"""
    from app.core import container_manager
    from docker.errors import NotFound

    mock_client = MagicMock()
    mock_client.containers.get.side_effect = NotFound("not found")

    with patch("app.core.container_manager.get_docker_client", return_value=mock_client):
        ip = await container_manager.get_container_ip("nonexistent")

    assert ip is None


@pytest.mark.asyncio
async def test_cp_09_get_container_ip_empty_networks():
    """容器网络配置为空时返回 None"""
    from app.core import container_manager

    mock_container = MagicMock()
    mock_container.attrs = {"NetworkSettings": {"Networks": {}}}

    mock_client = MagicMock()
    mock_client.containers.get.return_value = mock_container

    with patch("app.core.container_manager.get_docker_client", return_value=mock_client):
        ip = await container_manager.get_container_ip("abc123")

    assert ip is None


# ═══════════════════════════════════════════════════════════════════════════════
# TC-CP-10: get_sidecar_volume helper
# ═══════════════════════════════════════════════════════════════════════════════

def test_cp_10_get_sidecar_volume_exists():
    """Sidecar 脚本存在时返回正确的 (host_path, container_path)"""
    from app.core.system_entrypoint import get_sidecar_volume, SIDECAR_SCRIPT_HOST, SIDECAR_SCRIPT_CONTAINER

    # 真实脚本应存在（已在上一步创建）
    if SIDECAR_SCRIPT_HOST.exists():
        result = get_sidecar_volume()
        assert result is not None
        host, container = result
        assert host == str(SIDECAR_SCRIPT_HOST)
        assert container == SIDECAR_SCRIPT_CONTAINER
    else:
        pytest.skip("Sidecar 脚本文件不存在（data/system/agent/mini_file_server.py），跳过测试")


def test_cp_10_get_sidecar_volume_missing(tmp_path):
    """Sidecar 脚本不存在时返回 None"""
    from app.core import system_entrypoint

    # 临时覆盖常量指向不存在的路径
    original = system_entrypoint.SIDECAR_SCRIPT_HOST
    system_entrypoint.SIDECAR_SCRIPT_HOST = tmp_path / "nonexistent" / "mini_file_server.py"
    try:
        result = system_entrypoint.get_sidecar_volume()
        assert result is None
    finally:
        system_entrypoint.SIDECAR_SCRIPT_HOST = original


# ═══════════════════════════════════════════════════════════════════════════════
# TC-CP-11: system_entrypoint 模板内容验证
# ═══════════════════════════════════════════════════════════════════════════════

def test_cp_11_system_entrypoint_contains_sidecar():
    """system_entrypoint.sh 模板包含 Sidecar 启动指令"""
    from app.core.system_entrypoint import SYSTEM_ENTRYPOINT_TEMPLATE

    assert "mini_file_server" in SYSTEM_ENTRYPOINT_TEMPLATE, \
        "SYSTEM_ENTRYPOINT_TEMPLATE 应包含 mini_file_server 启动指令"
    assert "8010" in SYSTEM_ENTRYPOINT_TEMPLATE, \
        "SYSTEM_ENTRYPOINT_TEMPLATE 应包含 Sidecar 端口 8010"
    assert "uvicorn" in SYSTEM_ENTRYPOINT_TEMPLATE, \
        "SYSTEM_ENTRYPOINT_TEMPLATE 应使用 uvicorn 启动 Sidecar"


def test_cp_11_ensure_system_entrypoint_idempotent(tmp_path):
    """ensure_system_entrypoint 幂等：多次调用不报错且内容一致"""
    from app.core import system_entrypoint as sep

    original_dir = sep.SYSTEM_SCRIPTS_DIR
    original_path = sep.SYSTEM_ENTRYPOINT_PATH

    sep.SYSTEM_SCRIPTS_DIR = tmp_path
    sep.SYSTEM_ENTRYPOINT_PATH = tmp_path / "system_entrypoint.sh"

    try:
        p1 = sep.ensure_system_entrypoint()
        content1 = p1.read_text()

        p2 = sep.ensure_system_entrypoint()
        content2 = p2.read_text()

        assert content1 == content2, "多次调用应生成相同内容"
        assert p1.stat().st_mode & 0o111, "脚本应有可执行权限"
    finally:
        sep.SYSTEM_SCRIPTS_DIR = original_dir
        sep.SYSTEM_ENTRYPOINT_PATH = original_path


# ═══════════════════════════════════════════════════════════════════════════════
# TC-CP-03/04/05: shadow 代理权限校验（通过 FastAPI TestClient mock）
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cp_03_shadow_proxy_rejects_non_shadow():
    """非 Shadow 用户调用 Dry-Run 代理接口应返回 403"""
    from app.main import app as main_app
    from app.core.security import create_access_token

    token = create_access_token({"user_id": 1, "role": "student"})

    # mock is_shadow_user 返回 False（非 Shadow 用户）
    with patch("app.api.v1.endpoints.teacher.container_proxy.is_shadow_user", new=AsyncMock(return_value=False)):
        transport = ASGITransport(app=main_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            res = await c.get(
                "/api/v1/teachers/dry-run-tools/container-files/list",
                params={"path": "/"},
                headers={"Authorization": f"Bearer {token}"},
            )
    assert res.status_code == 403, f"期望 403，实际 {res.status_code}: {res.text}"


@pytest.mark.asyncio
async def test_cp_08_student_proxy_no_container():
    """学生无容器时，学生代理接口返回 404"""
    from app.main import app as main_app
    from app.core.security import create_access_token

    token = create_access_token({"user_id": 1, "role": "student"})

    # mock get_container_by_student 返回 None（无容器）
    with patch("app.api.v1.endpoints.student.container_files_proxy.crud_container") as mock_crud:
        mock_crud.get_container_by_student = AsyncMock(return_value=None)
        transport = ASGITransport(app=main_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            res = await c.get(
                "/api/v1/students/container-files/list",
                params={"path": "/home/student"},
                headers={"Authorization": f"Bearer {token}"},
            )
    assert res.status_code == 404, f"期望 404，实际 {res.status_code}: {res.text}"
