"""
Docker 客户端单例

连接策略：
1. 优先读取环境变量 DOCKER_HOST（支持远程 Docker）
2. 默认使用 unix:///var/run/docker.sock
"""
import docker
from docker import DockerClient
from docker.errors import DockerException
from typing import Optional

_client: Optional[DockerClient] = None


class DockerConnectionError(Exception):
    """Docker 守护进程连接失败"""
    pass


def get_docker_client() -> DockerClient:
    """
    获取 Docker 客户端（模块级单例）

    Raises:
        DockerConnectionError: Docker 守护进程不可达
    """
    global _client
    if _client is None:
        try:
            _client = docker.from_env(timeout=10)
            _client.ping()  # 验证连接
        except DockerException as e:
            _client = None
            raise DockerConnectionError(
                f"无法连接 Docker 守护进程: {e}"
            ) from e
    return _client
