# 测评脚本编写与输出规范 (Sidecar 执行引擎)

> **文档状态**：已发布
> **适用范围**：移动机器人实训数字孪生评价平台 - 测评脚本开发
> **核心架构**：Sidecar 容器 + 纯后端无头环境 (Headless) + JSON 结果闭环

---

## 1. 概述

本规范旨在指导平台教员和开发者编写标准化的测评脚本。所有测评脚本均在一个隔离的、无 UI 界面的 Docker Sidecar 容器中运行。脚本需要自动读取学生的代码快照、连接 ROS 环境进行动态/静态分析，并严格按照规定格式输出 `result.json`，以便平台闭环结算成绩。

## 2. 目录结构与入口约束

一个标准的测评脚本包通常包含以下结构：

```text
/opt/evaluate/                  # 容器内固定挂载的测评脚本目录
  ├── evaluate.sh               # 【必填】平台统一入口执行脚本
  ├── main_eval.py              # 【推荐】Python主评测逻辑（静态AST+动态ROS）
  └── requirements.txt          # 【可选】Python第三方依赖声明
```

### 2.1 环境变量约定

Sidecar 容器启动时，平台会注入以下环境变量，脚本**必须**通过读取这些变量来确定路径，严禁硬编码绝对路径：

| 环境变量名 | 默认值 / 示例 | 说明 |
| :--- | :--- | :--- |
| `SUBMISSION_DIR` | `/opt/submission` | 学生提交的代码快照根目录（只读） |
| `RESULT_PATH` | `/opt/artifacts/result.json` | 最终评测结果写入的绝对路径（读写） |
| `ROSBRIDGE_URL` | `ws://localhost:9090` | ROS Bridge WebSocket 连接地址 |
| `EXAM_ATTEMPT_ID` | `1024` | 当前考试运行记录的 ID |

## 3. 标准结果输出规范 (result.json)

无论评测成功还是因为异常中断，脚本**必须**在退出前向 `$RESULT_PATH` 写入符合以下 Schema 的 JSON 文件。若文件缺失、非合法 JSON 或缺少必填字段，平台将判定本次尝试为 `error` 状态。

### 3.1 字段定义

```json
{
  "status": "completed",       // 【必填】状态枚举: "completed" (正常完赛) 或 "failed" (脚本异常/未通过前置检查)
  "objective_score": 85.5,     // 【必填】客观得分，必须在 [0.0, 100.0] 闭区间内
  "pass": true,                // 【必填】是否通过考核 (布尔值)
  "summary": "综合评语...",      // 【必填】简短评语，严禁超过 500 字符
  "metrics": {                 // 【可选】平台通用指标字典，推荐包含以下基础指标
    "elapsed_seconds": 58.2,   // 实际运行时长 (秒)
    "goal_reached": true,      // 是否到达终点
    "collision_count": 0       // 碰撞次数
  },
  "artifacts": {},             // 【预留】产物文件索引，当前填空字典即可
  "custom_fields": {           // 【可选】私有字段，用于前端详情页渲染详细扣分项
    "errors": [],              // 评测过程中的非致命错误记录
    "dimension_scores": {}     // 多维度得分详情
  }
}
```

### 3.2 异常阻断时的输出处理

如果学生代码存在严重语法错误、环境依赖缺失或引发引擎崩溃，评测脚本需要利用 `try-except` 捕获异常，并输出 `status: "failed"` 的结果字典，**切勿让脚本直接 Crash 导致 `result.json` 丢失**。

## 4. 脚本编写模板

### 4.1 入口脚本 `evaluate.sh`

入口脚本负责初始化环境（尤其是 ROS 环境）、安装轻量依赖并拉起主评测程序。

```bash
#!/usr/bin/env bash
# evaluate.sh - 平台约定的唯一入口
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export RESULT_PATH="${RESULT_PATH:-/opt/artifacts/result.json}"
export SUBMISSION_DIR="${SUBMISSION_DIR:-/opt/submission}"
export ROSBRIDGE_URL="${ROSBRIDGE_URL:-ws://localhost:9090}"

# 1. 必须加载 ROS 环境
if [ -f "/opt/ros/noetic/setup.bash" ]; then
    source "/opt/ros/noetic/setup.bash"
else
    echo "[错误] 未找到 ROS Noetic 环境！"
    exit 1
fi

# 2. 安装 Python 依赖 (务必使用 --no-cache-dir 节省内存)
if [ -f "$SCRIPT_DIR/requirements.txt" ]; then
    pip3 install --no-cache-dir -q -r "$SCRIPT_DIR/requirements.txt"
fi

# 3. 执行 Python 评测主逻辑
echo "启动评测引擎..."
python3 "$SCRIPT_DIR/main_eval.py"
```

### 4.2 第三方依赖 `requirements.txt` 规范

Sidecar 属于无头环境，强烈建议安装 `headless` 版本的视觉库，避免拉取不必要的 GUI 依赖导致评测环境污染或报错。

```text
# 正确示例：
roslibpy>=1.3.0
psutil>=5.9.0
numpy>=1.20.0
opencv-python-headless>=4.5.0  # 绝对不要写成 opencv-python
```

## 5. 常见坑点与防范指南 (Best Practices)

### 5.1 防止无头环境 (Headless) 崩溃

**现象**：学生代码中常含有 `cv2.imshow()` 或 `cv2.namedWindow()` 等弹窗指令，在 Sidecar 容器中会触发 `The function is not implemented` 致命错误。
**防范**：测评底座在拉起学生代码前，应动态 Mock（劫持）这些 GUI 函数。

```python
# 在执行学生代码前注入：
import cv2
cv2.imshow = lambda *a, **k: None
cv2.namedWindow = lambda *a, **k: None
cv2.waitKey = lambda *a, **k: 1
cv2.destroyAllWindows = lambda *a, **k: None
```

### 5.2 避免 Bash 内联注入导致流缓冲丢失

在启动基于 ROS 循环的学生进程时，**不要**直接在 Bash 中使用 `python3 -c "..."` 进行内联启动，这会导致 stderr 错误堆栈丢失。
**正确做法**：使用 Python 的 `subprocess.Popen`，将 `stderr` 合并到 `stdout`，并注入 `PYTHONUNBUFFERED=1` 环境变量，使用子线程实时读取和打印日志。

### 5.3 严格的分数越界截断机制

为防止意外计算导致 JSON Schema 校验失败（如得出负分或超过 100 分），写入 JSON 前必须执行 Clamp 操作：

```python
raw_score = calculate_total()
# 强制截断至 0 - 100 闭区间
clamped_score = max(0.0, min(100.0, float(raw_score)))
# pass 字段必须是原生 bool 类型，不可为 numpy.bool_
is_passed = bool(clamped_score >= 60.0) 
```

### 5.4 防御性搜索目标文件

学生提交的代码文件名称和层级可能不完全统一，评测脚本不应写死绝对路径（如 `/opt/submission/src/main.py`），应使用递归搜索匹配。

```python
from pathlib import Path

def find_target_file(submission_dir: str):
    target_names = ["gazebo_line_follower.py", "line_follower.py"]
    base = Path(submission_dir)
    # 优先精确匹配
    for name in target_names:
        for match in base.rglob(name): return str(match)
    # 降级模糊匹配
    for match in base.rglob("*.py"):
        if "follower" in match.name.lower() or "line" in match.name.lower(): 
            return str(match)
    return None
```