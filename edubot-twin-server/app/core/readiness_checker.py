"""
readiness_checker — 容器就绪检测工具

通过宿主机侧 TCP 端口探测判断容器内服务就绪状态。
策略：每 2s 探测一次，最长等待 60s，分别检测 gzweb 和 rosbridge。

设计方案（10期补充SDD §3.3 方案 C1）：
- 简单可靠，不依赖容器内工具
- 宿主机 TCP 探测 + 超时兜底
"""
import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class ReadinessTimeout(Exception):
    """端口就绪超时异常"""
    def __init__(self, error_code: str, port: int, elapsed_ms: float):
        self.error_code = error_code
        self.port = port
        self.elapsed_ms = elapsed_ms
        super().__init__(f"{error_code}: 端口 {port} 在 {elapsed_ms:.0f}ms 内未就绪")


async def check_port_ready(
    host: str,
    port: int,
    timeout_s: float = 60.0,
    interval_s: float = 2.0,
) -> tuple[bool, float]:
    """
    TCP 端口就绪探测

    使用 asyncio.open_connection() 尝试 TCP 连接，连接成功即视为端口就绪。
    连接失败后等待 interval_s 后重试，直到 timeout_s 超时。

    :param host: 目标主机（"127.0.0.1" 或 "0.0.0.0"）
    :param port: 宿主机映射端口
    :param timeout_s: 最长等待时间（秒）
    :param interval_s: 重试间隔（秒）
    :returns: (is_ready, elapsed_ms)
    """
    start_time = time.perf_counter()

    while True:
        elapsed = time.perf_counter() - start_time
        if elapsed >= timeout_s:
            elapsed_ms = elapsed * 1000
            logger.warning(f"端口就绪检测超时: {host}:{port}，elapsed={elapsed_ms:.0f}ms")
            return False, elapsed_ms

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=3.0,  # 单次连接超时 3s
            )
            
            # 发送一个极简的 HTTP GET 请求，以验证内部是否存活。
            # 这是为了防止被 docker-proxy 欺骗：如果内部进程未启动，
            # docker-proxy 会接受 TCP 握手但随后立刻断开连接 (返回 EOF)。
            writer.write(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
            try:
                await writer.drain()
            except Exception:
                pass

            is_alive = False
            try:
                # 尝试读取至少1字节数据，0.5秒超时。
                # 由于 GzWeb 和 ROSBridge 都会响应正常的 HTTP/WS 请求，
                # 他们要么返回数据（如 HTTP 头），要么保持连接不放。
                # 唯独 docker-proxy 在后方不通的情况下会立刻发回 b'' (EOF) 并切断连接。
                data = await asyncio.wait_for(reader.read(1), timeout=0.5)
                is_alive = bool(data) 
            except asyncio.TimeoutError:
                # 如果 0.5s 后没有被切断，说明连接被真实进程维持，视为就绪
                is_alive = True
            except Exception:
                is_alive = False

            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

            if is_alive:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                logger.info(f"端口真实就绪: {host}:{port}，elapsed={elapsed_ms:.0f}ms")
                return True, elapsed_ms
            else:
                logger.debug(f"受到 docker-proxy 阻断或未响应 {host}:{port}，继续等待...")
                await asyncio.sleep(interval_s)

        except (ConnectionRefusedError, OSError, asyncio.TimeoutError):
            await asyncio.sleep(interval_s)


async def check_gzweb_ready(
    gz_port: int,
    host: str = "127.0.0.1",
    timeout_s: float = 60.0,
) -> tuple[bool, float]:
    """检测 gzweb HTTP 端口就绪"""
    logger.info(f"开始检测 gzweb 端口就绪: {host}:{gz_port}")
    return await check_port_ready(host, gz_port, timeout_s=timeout_s, interval_s=2.0)


async def check_rosbridge_ready(
    ros_port: int,
    host: str = "127.0.0.1",
    timeout_s: float = 60.0,
) -> tuple[bool, float]:
    """检测 rosbridge WebSocket 端口就绪"""
    logger.info(f"开始检测 rosbridge 端口就绪: {host}:{ros_port}")
    return await check_port_ready(host, ros_port, timeout_s=timeout_s, interval_s=2.0)
