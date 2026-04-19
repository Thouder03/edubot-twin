#!/usr/bin/env python3
"""仿真容器性能压测脚本

测试服务器能够并发运行多少组「仿真容器 + sidecar 评测容器」。

运行方式（推荐通过 sh 入口）：
    EXAM_ID=1 bash scripts/bench_sim_containers.sh [--step 2] [--max 30] [--stabilize 30]
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests


# ─── 数据结构 ─────────────────────────────────────────────────────────

@dataclass
class StudentInfo:
    id: int
    username: str


@dataclass
class ContainerInfo:
    container_name: str        # Docker 容器名 edubot-sim-{student_id}，用于 stats 查询
    status: str                # succeeded / failed
    error: Optional[str] = None
    rosbridge_url: Optional[str] = None  # ws://host:port，用于 WebSocket 模拟连接


@dataclass
class ContainerStats:
    cpu_pct: float
    mem_mb: float


# ─── API 客户端 ────────────────────────────────────────────────────────

class BenchClient:
    """封装与后端 API 的交互。"""

    def __init__(self, api_base: str, teacher_user: str, teacher_pass: str):
        self.api_base = api_base.rstrip("/")
        self._teacher_user = teacher_user
        self._teacher_pass = teacher_pass
        self._session = requests.Session()
        self._session.headers["Content-Type"] = "application/json"

    def login(self) -> None:
        resp = self._session.post(
            f"{self.api_base}/auth/token",
            json={"username": self._teacher_user, "password": self._teacher_pass},
            timeout=10,
        )
        resp.raise_for_status()
        token = resp.json()["data"]["access_token"]
        self._session.headers["Authorization"] = f"Bearer {token}"

    def _req(self, method: str, path: str, **kwargs) -> dict:
        resp = self._session.request(method, f"{self.api_base}{path}", **kwargs)
        if not resp.ok:
            try:
                detail = resp.json()
            except Exception:
                detail = resp.text[:200]
            raise requests.HTTPError(
                f"{resp.status_code} {resp.reason}: {detail}", response=resp,
            )
        return resp.json()

    def _student_req(self, method: str, path: str, token: str, **kwargs) -> dict:
        resp = self._session.request(
            method, f"{self.api_base}{path}",
            headers={"Authorization": f"Bearer {token}"},
            **kwargs,
        )
        if not resp.ok:
            try:
                detail = resp.json()
            except Exception:
                detail = resp.text[:200]
            raise requests.HTTPError(
                f"{resp.status_code} {resp.reason}: {detail}", response=resp,
            )
        return resp.json()

    # ── 教师操作 ──────────────────────────────────────────────────────

    def get_exam(self, exam_id: int) -> dict:
        return self._req("GET", f"/teachers/exams/{exam_id}", timeout=10)["data"]

    def get_student_by_username(self, username: str) -> Optional[StudentInfo]:
        data = self._req(
            "GET", f"/teachers/students?pageIndex=1&pageSize=1&keyword={username}",
            timeout=10,
        )
        for item in data["data"]["list"]:
            if item["username"] == username:
                return StudentInfo(id=item["id"], username=username)
        return None

    def create_student(self, username: str) -> StudentInfo:
        """创建学生。若账号已存在则先删除再重建，确保干净状态（无残留容器）。"""
        try:
            data = self._req(
                "POST", "/teachers/students",
                json={"username": username, "password": username, "role_code": "student"},
                timeout=15,
            )
            return StudentInfo(id=data["data"]["id"], username=username)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 400:
                existing = self.get_student_by_username(username)
                if existing:
                    print(f"      (清理残留账号后重建: {username})")
                    self.delete_student(existing.id)
                    data = self._req(
                        "POST", "/teachers/students",
                        json={"username": username, "password": username, "role_code": "student"},
                        timeout=15,
                    )
                    return StudentInfo(id=data["data"]["id"], username=username)
            raise

    def delete_student(self, student_id: int) -> None:
        """删除学生（级联删除 Docker 容器）。失败时抛出异常由调用方处理。"""
        self._req("DELETE", f"/teachers/students/{student_id}", timeout=30)

    # ── 学生操作 ──────────────────────────────────────────────────────

    def student_login(self, username: str) -> str:
        resp = self._session.post(
            f"{self.api_base}/auth/token",
            json={"username": username, "password": username},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["data"]["access_token"]

    def start_exam_container(self, exam_id: int, token: str) -> str:
        """
        POST /students/simulation/start-exam-container
        异步启动考试专用容器，返回 task_id。
        """
        data = self._student_req(
            "POST", "/students/simulation/start-exam-container", token,
            json={"exam_id": exam_id}, timeout=15,
        )
        return data["data"]["task_id"]

    def poll_task(self, task_id: str, token: str) -> dict:
        """GET /students/tasks/{task_id}，返回 task 数据。"""
        return self._student_req(
            "GET", f"/students/tasks/{task_id}", token, timeout=10,
        )["data"]

    def get_my_container(self, token: str) -> Optional[dict]:
        """GET /students/container/mine，返回容器数据或 None。"""
        data = self._student_req("GET", "/students/container/mine", token, timeout=10)
        return data.get("data")

    def create_attempt(self, exam_id: int, token: str) -> int:
        data = self._student_req(
            "POST", "/students/exam-attempts", token,
            json={"exam_id": exam_id}, timeout=15,
        )
        return data["data"]["attempt_id"]

    def start_attempt(self, attempt_id: int, token: str) -> None:
        self._student_req(
            "POST", f"/students/exam-attempts/{attempt_id}/start", token,
            timeout=30,
        )


# ─── 心跳管理 ─────────────────────────────────────────────────────────

class HeartbeatManager:
    """
    后台守护线程：每隔 interval 秒为所有已注册的学生容器发送心跳。
    服务器心跳超时为 120s，interval 默认 60s（留足余量）。
    """

    def __init__(self, client: "BenchClient", interval: int = 60):
        self._client = client
        self._interval = interval
        self._tokens: dict[str, str] = {}  # username -> student_token
        self._lock = threading.Lock()
        self._stop_evt = threading.Event()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="heartbeat"
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_evt.set()
        self._thread.join(timeout=5)

    def register(self, username: str, token: str) -> None:
        with self._lock:
            self._tokens[username] = token

    def unregister(self, username: str) -> None:
        with self._lock:
            self._tokens.pop(username, None)

    def _run(self) -> None:
        while not self._stop_evt.wait(self._interval):
            with self._lock:
                items = list(self._tokens.items())
            for _, token in items:
                try:
                    self._client._student_req(
                        "POST", "/students/container/heartbeat", token, timeout=5,
                    )
                except Exception:
                    pass  # 单次心跳失败不影响测试，下轮重试


# ─── Rosbridge 模拟连接 ────────────────────────────────────────────────

class RosbridgeSimulator:
    """
    为每个仿真容器维持一条 rosbridge WebSocket 长连接，订阅与 3D 面板相同的话题，
    模拟真实学生前端（roslibjs）产生的 rosbridge 序列化和推送 CPU 负载。

    订阅策略与 ROS3DViewer/index.vue getTopicOptions() 保持一致：
      /tf, /tf_static, /clock → 100ms throttle, queue_length=1, cbor
      /scan (LaserScan)       → 100ms throttle, queue_length=1, cbor
    """

    # 与前端 3D 面板完全一致的订阅消息列表
    _SUBSCRIPTIONS: list[str] = [
        json.dumps({"op": "subscribe", "topic": "/tf",
                    "type": "tf2_msgs/TFMessage",
                    "throttle_rate": 100, "queue_length": 1, "compression": "cbor"}),
        json.dumps({"op": "subscribe", "topic": "/tf_static",
                    "type": "tf2_msgs/TFMessage",
                    "throttle_rate": 100, "queue_length": 1, "compression": "cbor"}),
        json.dumps({"op": "subscribe", "topic": "/clock",
                    "type": "rosgraph_msgs/Clock",
                    "throttle_rate": 100, "queue_length": 1, "compression": "cbor"}),
        json.dumps({"op": "subscribe", "topic": "/scan",
                    "type": "sensor_msgs/LaserScan",
                    "throttle_rate": 100, "queue_length": 1, "compression": "cbor"}),
    ]

    def __init__(self) -> None:
        self._stop_events: dict[str, threading.Event] = {}
        self._threads: dict[str, threading.Thread] = {}

    def connect(self, username: str, rosbridge_url: str) -> None:
        """为指定学生建立 WebSocket 连接（在独立守护线程中运行）。"""
        stop_evt = threading.Event()
        self._stop_events[username] = stop_evt
        t = threading.Thread(
            target=self._run,
            args=(username, rosbridge_url, stop_evt),
            daemon=True,
            name=f"ros-{username}",
        )
        t.start()
        self._threads[username] = t

    def close_all(self) -> None:
        """发出停止信号，等待所有连接线程退出。"""
        for evt in self._stop_events.values():
            evt.set()
        for t in self._threads.values():
            t.join(timeout=5)
        self._stop_events.clear()
        self._threads.clear()

    def _run(self, username: str, url: str, stop_evt: threading.Event) -> None:
        from websockets.sync.client import connect as ws_connect
        try:
            with ws_connect(url, open_timeout=15) as ws:
                for msg in self._SUBSCRIPTIONS:
                    ws.send(msg)
                # cbor 消息为二进制帧，直接接收丢弃即可（rosbridge 已完成序列化）
                while not stop_evt.is_set():
                    try:
                        ws.recv(timeout=1)
                    except TimeoutError:
                        pass
        except Exception:
            pass  # 连接失败或断开静默处理，不影响测试主流程


# ─── 资源采集 ──────────────────────────────────────────────────────────

def _parse_mem_to_mb(mem_str: str) -> float:
    s = mem_str.strip().upper()
    if not s or s in ("0B", "0"):
        return 0.0
    for suffix, factor in [
        ("GIB", 1024.0), ("MIB", 1.0), ("GI", 1024.0), ("MI", 1.0),
        ("GB", 953.674), ("MB", 0.953674),
        ("KIB", 1.0 / 1024), ("KB", 1.0 / 1024), ("B", 1.0 / 1024 / 1024),
    ]:
        if s.endswith(suffix):
            try:
                return float(s[: -len(suffix)]) * factor
            except ValueError:
                return 0.0
    return 0.0


def _parse_stats_output(output: str) -> list[ContainerStats]:
    stats = []
    for line in output.strip().splitlines():
        if not line:
            continue
        try:
            s = json.loads(line)
            cpu_str = s.get("CPUPerc", "0%").replace("%", "").strip()
            mem_str = s.get("MemUsage", "0B / 0B").split("/")[0].strip()
            cpu = float(cpu_str) if cpu_str else 0.0
            stats.append(ContainerStats(cpu_pct=cpu, mem_mb=_parse_mem_to_mb(mem_str)))
        except (json.JSONDecodeError, ValueError):
            continue
    return stats


def _docker_stats(container_names: list[str]) -> list[ContainerStats]:
    """按名称逐个查询，跳过不存在或已停止的容器，避免整批失败。"""
    if not container_names:
        return []
    stats: list[ContainerStats] = []
    # 一次性查询，docker stats 对不存在的容器会在 stderr 报错但仍输出其他容器数据
    try:
        r = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{json .}}"] + container_names,
            capture_output=True, text=True, timeout=15,
        )
        stats = _parse_stats_output(r.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return stats


def _get_sidecar_ids() -> list[str]:
    try:
        r = subprocess.run(
            ["docker", "ps", "--filter", "name=sidecar-exam-", "--format", "{{.ID}}"],
            capture_output=True, text=True, timeout=5,
        )
        return [line.strip() for line in r.stdout.strip().splitlines() if line.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def _read_cpu_stat() -> tuple[int, int]:
    line = open("/proc/stat").readline()
    vals = list(map(int, line.split()[1:8]))
    return sum(vals), vals[3] + vals[4]  # (total, idle+iowait)


def host_cpu_percent(interval: float = 1.0) -> float:
    t1, i1 = _read_cpu_stat()
    time.sleep(interval)
    t2, i2 = _read_cpu_stat()
    delta_total = t2 - t1
    if delta_total == 0:
        return 0.0
    return 100.0 * (1.0 - (i2 - i1) / delta_total)


def host_mem_percent() -> float:
    info: dict[str, int] = {}
    for line in open("/proc/meminfo"):
        parts = line.split()
        if len(parts) >= 2:
            info[parts[0].rstrip(":")] = int(parts[1])
    total = info.get("MemTotal", 1)
    available = info.get("MemAvailable", 0)
    return 100.0 * (1.0 - available / total)


def sample_resources(sim_container_names: list[str]) -> dict:
    host_cpu = host_cpu_percent(interval=1.0)
    host_mem = host_mem_percent()
    sim_stats = _docker_stats(sim_container_names)
    sidecar_ids = _get_sidecar_ids()
    sidecar_stats = _docker_stats(sidecar_ids)
    sim_cpu_total = round(sum(s.cpu_pct for s in sim_stats), 1)
    sidecar_cpu_total = round(sum(s.cpu_pct for s in sidecar_stats), 1)
    return {
        "host_cpu_pct": round(host_cpu, 1),
        "host_mem_pct": round(host_mem, 1),
        "total_container_cpu_pct": round(sim_cpu_total + sidecar_cpu_total, 1),
        "sim_stats": [{"cpu_pct": s.cpu_pct, "mem_mb": round(s.mem_mb, 1)} for s in sim_stats],
        "sidecar_stats": [{"cpu_pct": s.cpu_pct, "mem_mb": round(s.mem_mb, 1)} for s in sidecar_stats],
        "sidecar_count": len(sidecar_stats),
    }


# ─── 主测试逻辑 ────────────────────────────────────────────────────────

def wait_for_task(
    client: BenchClient, task_id: str, token: str, timeout: int
) -> tuple[bool, Optional[str]]:
    """
    轮询 GET /students/tasks/{task_id}，直到 SUCCEEDED 或 FAILED 或超时。
    返回 (succeeded, error_info)。
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            task = client.poll_task(task_id, token)
        except Exception as e:
            time.sleep(3)
            continue
        status = task.get("task_status", "")
        if status == "SUCCEEDED":
            return True, None
        if status == "FAILED":
            err = task.get("error_code") or task.get("error_message") or "FAILED"
            return False, err
        time.sleep(3)
    return False, "TIMEOUT"


def start_container_for_student(
    client: BenchClient,
    student: StudentInfo,
    exam_id: int,
    task_timeout: int,
    hb: HeartbeatManager,
) -> tuple[StudentInfo, ContainerInfo, str]:
    """
    完整的单学生容器启动流程：
      1. 学生登录
      2. POST /students/simulation/start-exam-container → task_id
      3. 轮询 task 直到 SUCCEEDED/FAILED
      4. SUCCEEDED 时注册心跳 + GET /students/container/mine → docker_id

    返回 (student, ContainerInfo, student_token)。
    """
    token = client.student_login(student.username)

    task_id = client.start_exam_container(exam_id, token)
    succeeded, err = wait_for_task(client, task_id, token, timeout=task_timeout)

    # 容器名由 container_manager 按固定规则生成，无需从 API 取
    container_name = f"edubot-sim-{student.id}"

    if not succeeded:
        return student, ContainerInfo(container_name=container_name, status="failed", error=err), token

    # 容器就绪后立即注册心跳，防止超时被回收
    hb.register(student.username, token)

    # 获取 rosbridge_url 用于 WebSocket 模拟连接
    rosbridge_url: Optional[str] = None
    try:
        container_data = client.get_my_container(token)
        if container_data:
            rosbridge_url = container_data.get("rosbridge_url")
    except Exception:
        pass

    return student, ContainerInfo(
        container_name=container_name, status="succeeded", rosbridge_url=rosbridge_url
    ), token


def run_round(
    client: BenchClient,
    exam_id: int,
    new_students: list[StudentInfo],
    all_sim_docker_ids: list[str],
    stabilize_sec: int,
    log_dir: Path,
    total_n: int,
    task_timeout: int = 180,
    hb: Optional[HeartbeatManager] = None,
    ros_sim: Optional[RosbridgeSimulator] = None,
) -> tuple[dict, list[ContainerInfo]]:
    """执行一轮测试，返回 (resources_snapshot, new_containers)。"""
    step = len(new_students)
    t0 = time.monotonic()

    # (a) 并发启动考试容器，等待 task 完成
    print(f"  (a) 并发启动 {step} 个考试容器（POST /simulation/start-exam-container）...")
    results: list[tuple[StudentInfo, ContainerInfo, str]] = []
    with ThreadPoolExecutor(max_workers=min(step, 8)) as pool:
        idx_futs = {
            pool.submit(start_container_for_student, client, s, exam_id, task_timeout, hb): i
            for i, s in enumerate(new_students)
        }
        ordered: list[Optional[tuple[StudentInfo, ContainerInfo, str]]] = [None] * step
        for fut in as_completed(idx_futs):
            i = idx_futs[fut]
            try:
                ordered[i] = fut.result()
            except Exception as e:
                student = new_students[i]
                print(f"      ⚠ {student.username} 启动异常: {e}")
                ordered[i] = (student, ContainerInfo(docker_id=None, status="failed", error=str(e)), "")
        results = [r for r in ordered if r is not None]

    ok_results = [(s, c, tok) for s, c, tok in results if c.status == "succeeded"]
    elapsed_start = time.monotonic() - t0
    print(f"      成功 {len(ok_results)}/{step}，耗时 {elapsed_start:.1f}s")
    for s, c, _ in results:
        if c.status == "failed":
            print(f"      ⚠ {s.username} 容器启动失败: {c.error}")

    # (b) 并发启动考试尝试（触发 sidecar）+ 建立 rosbridge 模拟连接
    if ok_results:
        print(f"  (b) 并发启动 {len(ok_results)} 个考试尝试...")

        def _start_exam(s: StudentInfo, tok: str) -> None:
            attempt_id = client.create_attempt(exam_id, tok)
            client.start_attempt(attempt_id, tok)

        with ThreadPoolExecutor(max_workers=min(len(ok_results), 8)) as pool:
            futs = {pool.submit(_start_exam, s, tok): s for s, _, tok in ok_results}
            for fut in as_completed(futs):
                s = futs[fut]
                try:
                    fut.result()
                except Exception as e:
                    print(f"      ⚠ {s.username} 考试启动失败: {e}")

        # 为每个成功的容器建立 rosbridge WebSocket 长连接
        if ros_sim:
            connected = 0
            for s, c, _ in ok_results:
                if c.rosbridge_url:
                    ros_sim.connect(s.username, c.rosbridge_url)
                    connected += 1
            if connected:
                print(f"  (b.1) 已发起 {connected} 个 rosbridge WebSocket 连接")

    # (c) 稳定期
    print(f"  (c) 稳定期 {stabilize_sec}s...")
    time.sleep(stabilize_sec)

    # (d) 采集资源快照
    print("  (d) 采集资源快照...")
    new_names = [c.container_name for _, c, _ in ok_results]
    current_sim_names = all_sim_docker_ids + new_names  # all_sim_docker_ids 此处存放 container_name
    resources = sample_resources(current_sim_names)
    resources["startup_duration_s"] = round(time.monotonic() - t0, 1)
    resources["failed_containers"] = step - len(ok_results)
    resources["total_n"] = total_n

    (log_dir / f"round_{total_n:03d}.json").write_text(
        json.dumps(resources, ensure_ascii=False, indent=2)
    )

    new_containers = [c for _, c, _ in results]
    return resources, new_containers


def cleanup_sidecar_containers() -> None:
    """强制删除所有名称以 sidecar-exam- 开头的容器（运行中或已停止）。"""
    try:
        r = subprocess.run(
            ["docker", "ps", "-a", "--filter", "name=sidecar-exam-", "--format", "{{.ID}}"],
            capture_output=True, text=True, timeout=5,
        )
        ids = [line.strip() for line in r.stdout.strip().splitlines() if line.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        ids = []

    if not ids:
        print("  sidecar 容器：无需清理")
        return

    print(f"  强制删除 {len(ids)} 个 sidecar 容器...")
    try:
        subprocess.run(
            ["docker", "rm", "-f"] + ids,
            capture_output=True, timeout=30,
        )
        print(f"  sidecar 容器已清理")
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"  ⚠ sidecar 清理失败: {e}")


def cleanup(client: BenchClient, all_students: list[StudentInfo]) -> None:
    print(f"\n─── 清理 {len(all_students)} 个测试学生账号（级联删除 Docker 容器）...")
    failed: list[StudentInfo] = []

    def _delete_one(s: StudentInfo) -> Optional[str]:
        """返回错误信息，成功返回 None。"""
        try:
            client.delete_student(s.id)
            return None
        except Exception as e:
            return str(e)

    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(_delete_one, s): s for s in all_students}
        for fut in as_completed(futs):
            s = futs[fut]
            err = fut.result()
            if err:
                print(f"  ⚠ 删除 {s.username}(id={s.id}) 失败: {err}")
                failed.append(s)

    # 失败的账号等 3s 后重试一次（可能是容器仍在停止中）
    if failed:
        print(f"  重试删除 {len(failed)} 个失败账号...")
        time.sleep(3)
        still_failed: list[StudentInfo] = []
        for s in failed:
            err = _delete_one(s)
            if err:
                print(f"  ✗ 重试仍失败 {s.username}(id={s.id}): {err}")
                still_failed.append(s)
            else:
                print(f"  ✓ 重试成功: {s.username}")
        if still_failed:
            names = ", ".join(s.username for s in still_failed)
            print(f"  ⚠ 以下账号需手动删除: {names}")
        else:
            print("  重试全部成功。")
    else:
        print("  清理完成。")


# ─── 报告打印 ─────────────────────────────────────────────────────────

_HEADER = (
    f"{'N':>4}  {'耗时':>7}  {'主机CPU':>7}  {'主机MEM':>7}  "
    f"{'容器CPU合计':>10}  {'仿真CPU':>8}  {'SidecarCPU':>10}  {'仿真MEM均MB':>10}  {'失败/总数':>8}"
)
_SEP = "─" * len(_HEADER)


def _agg(stats: list[dict]) -> tuple[float, float]:
    if not stats:
        return 0.0, 0.0
    return round(sum(s["cpu_pct"] for s in stats), 1), round(
        sum(s["mem_mb"] for s in stats) / len(stats), 1
    )


def print_row(n: int, resources: dict, report_file, threshold_hit: bool = False) -> None:
    sim_cpu, sim_mem = _agg(resources.get("sim_stats", []))
    sidecar_cpu, _ = _agg(resources.get("sidecar_stats", []))
    total_cpu = resources.get("total_container_cpu_pct", round(sim_cpu + sidecar_cpu, 1))
    flag = "  ← 阈值" if threshold_hit else ""
    row = (
        f"{n:>4}  {resources['startup_duration_s']:>6.1f}s"
        f"  {resources['host_cpu_pct']:>6.1f}%  {resources['host_mem_pct']:>6.1f}%"
        f"  {total_cpu:>9.1f}%  {sim_cpu:>7.1f}%  {sidecar_cpu:>9.1f}%"
        f"  {sim_mem:>9.1f}  {resources['failed_containers']:>3}/{n}{flag}"
    )
    print(row)
    report_file.write(row + "\n")


# ─── 主入口 ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="仿真容器性能压测")
    parser.add_argument("--exam-id", type=int, required=True)
    parser.add_argument("--step", type=int, default=2, help="每轮新增容器组数（默认 2）")
    parser.add_argument("--max", type=int, default=30, help="最大测试容器组数（默认 30）")
    parser.add_argument("--stabilize", type=int, default=30, help="每轮稳定等待秒数（默认 30）")
    parser.add_argument("--cpu-threshold", type=float, default=85.0)
    parser.add_argument("--mem-threshold", type=float, default=85.0)
    parser.add_argument("--api-base", default="http://localhost:8000/api/v1")
    parser.add_argument("--teacher-user", default="teacher")
    parser.add_argument("--teacher-pass", default="teacher")
    parser.add_argument("--task-timeout", type=int, default=180,
                        help="单个容器启动任务超时秒数（默认 180）")
    parser.add_argument("--no-cleanup", action="store_true", help="结束后保留容器（调试）")
    args = parser.parse_args()

    exam_id = args.exam_id

    # 巡线脚本路径和学生工作区根目录
    EXAM_SCRIPT_SRC = Path("scripts/gazebo_line_follower.py")
    STUDENTS_DATA_ROOT = Path("edubot-twin-server/data/students")

    if not EXAM_SCRIPT_SRC.exists():
        print(f"错误：巡线脚本不存在：{EXAM_SCRIPT_SRC.resolve()}")
        sys.exit(1)

    def setup_student_workspace(student_id: int) -> None:
        dest_dir = STUDENTS_DATA_ROOT / str(student_id) / "workspace" / "scripts"
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(EXAM_SCRIPT_SRC, dest_dir / EXAM_SCRIPT_SRC.name)

    log_dir = Path("logs") / f"bench_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    log_dir.mkdir(parents=True, exist_ok=True)
    report_path = log_dir / "report.txt"

    print("═" * 80)
    print(f"  仿真容器性能压测   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  考试 ID: {exam_id}   步长: {args.step}   上限: {args.max}   稳定期: {args.stabilize}s")
    print(f"  CPU 阈值: {args.cpu_threshold}%   内存阈值: {args.mem_threshold}%   任务超时: {args.task_timeout}s")
    print(f"  日志目录: {log_dir}")
    print("═" * 80)

    client = BenchClient(args.api_base, args.teacher_user, args.teacher_pass)

    print("\n[初始化] 教师登录...")
    client.login()

    print("[初始化] 验证考试...")
    exam = client.get_exam(exam_id)
    if exam["status"] != "published":
        print(f"  ✗ 考试状态为 '{exam['status']}'，必须为 published，终止测试")
        sys.exit(1)
    print(f"  ✓ 考试: {exam['name']}  模式: {exam['exam_mode']}")

    all_students: list[StudentInfo] = []
    all_sim_container_names: list[str] = []  # edubot-sim-{student_id} 列表，用于 docker stats
    last_ok_n = 0
    threshold_hit = False
    threshold_reason = ""
    interrupted = False

    hb = HeartbeatManager(client, interval=60)
    hb.start()
    ros_sim = RosbridgeSimulator()

    def _do_cleanup() -> None:
        hb.stop()
        ros_sim.close_all()
        cleanup_sidecar_containers()
        if args.no_cleanup:
            if all_students:
                last = f"bench_stu_{len(all_students):03d}"
                print(f"(--no-cleanup 已保留容器，手动清理：删除学生账号 bench_stu_001 ~ {last})")
        elif all_students:
            cleanup(client, all_students)

    try:
        with open(report_path, "w") as report_file:
            report_file.write(
                f"仿真容器性能压测报告  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"考试 ID: {exam_id}  名称: {exam['name']}\n\n"
            )
            report_file.write(_SEP + "\n" + _HEADER + "\n" + _SEP + "\n")
            print(f"\n{_SEP}\n{_HEADER}\n{_SEP}")

            n = args.step
            while n <= args.max:
                prev_total = len(all_students)
                print(f"\n[轮次 N={n}] 创建 {args.step} 个新学生账号...")
                new_students: list[StudentInfo] = []
                for i in range(prev_total + 1, prev_total + args.step + 1):
                    username = f"bench_stu_{i:03d}"
                    try:
                        s = client.create_student(username)
                        setup_student_workspace(s.id)
                        new_students.append(s)
                        all_students.append(s)
                    except Exception as e:
                        print(f"    ⚠ 创建学生 {username} 失败: {e}")

                if not new_students:
                    print("  ✗ 无法创建新学生账号，终止测试")
                    break

                resources, new_containers = run_round(
                    client, exam_id, new_students,
                    all_sim_container_names, args.stabilize, log_dir, n,
                    task_timeout=args.task_timeout,
                    hb=hb,
                    ros_sim=ros_sim,
                )

                for c in new_containers:
                    if c.status == "succeeded":
                        all_sim_container_names.append(c.container_name)

                fail_ratio = resources["failed_containers"] / args.step
                if resources["host_cpu_pct"] > args.cpu_threshold:
                    threshold_hit = True
                    threshold_reason = f"主机 CPU {resources['host_cpu_pct']:.1f}% > {args.cpu_threshold}%"
                elif resources["host_mem_pct"] > args.mem_threshold:
                    threshold_hit = True
                    threshold_reason = f"主机内存 {resources['host_mem_pct']:.1f}% > {args.mem_threshold}%"
                elif fail_ratio > 0.5:
                    threshold_hit = True
                    threshold_reason = f"失败率 {fail_ratio * 100:.0f}% > 50%"

                print_row(n, resources, report_file, threshold_hit)
                report_file.flush()

                if not threshold_hit:
                    last_ok_n = n

                if threshold_hit:
                    print(f"\n  ⚠ 触达阈值：{threshold_reason}")
                    break

                n += args.step

            print(_SEP)
            report_file.write(_SEP + "\n")

            try:
                ncpu = os.cpu_count() or 0
                load_str = " ".join(open("/proc/loadavg").read().split()[:3])
            except Exception:
                ncpu, load_str = 0, "N/A"

            summary = (
                f"\n建议最大并发组数：{last_ok_n}（仿真容器×{last_ok_n} + sidecar×{last_ok_n}）\n"
            )
            if threshold_reason:
                summary += f"资源瓶颈：{threshold_reason}\n"
            summary += f"主机 CPU 核心数：{ncpu}   最终负载均值：{load_str}\n"
            print(summary)
            report_file.write(summary)

    except KeyboardInterrupt:
        interrupted = True
        print("\n\n  ⚠ 用户中断（Ctrl+C），正在执行善后清理...")

    _do_cleanup()
    print(f"报告已保存至：{report_path}")

    if interrupted:
        sys.exit(130)  # 标准 SIGINT 退出码


if __name__ == "__main__":
    main()
