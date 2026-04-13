"""
Sidecar 标准 JSON 结果解析与 Schema 校验（第12期 S5）

SDD §7.3 校验规则：
1. result.json 文件必须存在 → RESULT_MISSING_FILE
2. 必须是合法 JSON → RESULT_INVALID_JSON
3. 必填字段缺失 → RESULT_MISSING_FIELDS，error_message 列出缺失项
4. objective_score 必须在 [0, 100]，超界 clamp 并记录 system_warning
5. 未知字段容忍（向前兼容）
6. 文件大小上限 1MB → RESULT_TOO_LARGE
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 文件大小上限（字节）
MAX_RESULT_FILE_BYTES = 1 * 1024 * 1024  # 1MB

# 必填字段
REQUIRED_FIELDS = {"status", "objective_score", "pass", "summary"}


class ParseError(Exception):
    """解析失败（含错误码）"""
    def __init__(self, message: str, error_code: str):
        super().__init__(message)
        self.error_code = error_code


@dataclass
class ParseResult:
    """解析成功结果"""
    raw: dict                           # 原始 JSON 对象
    status: str                         # completed / failed
    objective_score: float              # 已 clamp 到 [0, 100]
    pass_: bool                         # 是否通过
    summary: str                        # 评语
    metrics: Optional[dict] = None
    artifacts: Optional[dict] = None
    custom_fields: Optional[dict] = None
    score_clamped: bool = False         # 是否触发了 clamp（触发时需记录 system_warning）
    missing_optional: list[str] = field(default_factory=list)


def parse_result_json(artifacts_path: str) -> ParseResult:
    """
    读取并校验 result.json。

    同步执行（由调用方包装到 asyncio executor 中）。

    Args:
        artifacts_path: Sidecar artifacts 目录路径（/data/exam_artifacts/{attempt_id}/）

    Returns:
        ParseResult

    Raises:
        ParseError: 校验失败，含 error_code 和 message
    """
    result_file = Path(artifacts_path) / "result.json"

    # 1. 文件存在性检查
    if not result_file.exists():
        raise ParseError(
            f"result.json 不存在于 {artifacts_path}",
            error_code="RESULT_MISSING_FILE",
        )

    # 2. 文件大小检查
    file_size = result_file.stat().st_size
    if file_size > MAX_RESULT_FILE_BYTES:
        raise ParseError(
            f"result.json 超过大小上限（{file_size} > {MAX_RESULT_FILE_BYTES} bytes）",
            error_code="RESULT_TOO_LARGE",
        )

    # 3. JSON 合法性检查
    try:
        content = result_file.read_text(encoding="utf-8")
        raw: dict[str, Any] = json.loads(content)
    except json.JSONDecodeError as e:
        raise ParseError(
            f"result.json 非合法 JSON：{e}",
            error_code="RESULT_INVALID_JSON",
        ) from e
    except OSError as e:
        raise ParseError(
            f"读取 result.json 失败：{e}",
            error_code="RESULT_INVALID_JSON",
        ) from e

    # 4. 必填字段校验
    missing = [f for f in REQUIRED_FIELDS if f not in raw]
    if missing:
        raise ParseError(
            f"result.json 缺少必填字段：{missing}",
            error_code="RESULT_MISSING_FIELDS",
        )

    # 5. 类型与值校验
    try:
        objective_score = float(raw["objective_score"])
    except (TypeError, ValueError) as e:
        raise ParseError(
            f"objective_score 不是数值：{raw.get('objective_score')}",
            error_code="RESULT_MISSING_FIELDS",
        ) from e

    # Clamp 到 [0, 100]
    score_clamped = False
    if objective_score < 0 or objective_score > 100:
        logger.warning(
            f"[result_parser] objective_score={objective_score} 超出 [0,100]，执行 clamp"
        )
        objective_score = max(0.0, min(100.0, objective_score))
        score_clamped = True

    try:
        pass_ = bool(raw["pass"])
    except (TypeError, ValueError) as e:
        raise ParseError(
            f"pass 不是布尔值：{raw.get('pass')}",
            error_code="RESULT_MISSING_FIELDS",
        ) from e

    summary = str(raw.get("summary", ""))[:500]
    status = str(raw.get("status", "completed"))

    # 6. 提取可选字段（容忍未知字段）
    metrics = raw.get("metrics") if isinstance(raw.get("metrics"), dict) else None
    artifacts_index = raw.get("artifacts") if isinstance(raw.get("artifacts"), dict) else None
    custom_fields = raw.get("custom_fields") if isinstance(raw.get("custom_fields"), dict) else None

    logger.info(
        f"[result_parser] 解析成功 "
        f"status={status} score={objective_score} pass={pass_} "
        f"clamped={score_clamped}"
    )

    return ParseResult(
        raw=raw,
        status=status,
        objective_score=objective_score,
        pass_=pass_,
        summary=summary,
        metrics=metrics,
        artifacts=artifacts_index,
        custom_fields=custom_fields,
        score_clamped=score_clamped,
    )
