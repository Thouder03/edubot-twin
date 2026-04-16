"""
最终成绩核算器（第13期 SDD §5.2）

公式：
    final_score = objective_score × weight_objective
                + manual_score   × weight_manual
    pass_final  = final_score ≥ pass_threshold

评分模式（scoring_mode）：
    objective_only  纯客观分，weight_objective=1.0，不需要人工评分
    mixed           混合评分，按 manual_score_ratio(%) 拆分权重

覆盖场景（allow_override_*）见 calculate_with_override()。
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ─── 默认策略值（与第11/12期 scoring_policy 默认值对齐）─────────────────────


DEFAULT_SCORING_MODE = "objective_only"
DEFAULT_WEIGHT_OBJECTIVE = 1.0  # 默认全靠客观分
DEFAULT_WEIGHT_MANUAL = 0.0
DEFAULT_PASS_THRESHOLD = 60.0
DEFAULT_ALLOW_OVERRIDE_OBJECTIVE = False
DEFAULT_ALLOW_OVERRIDE_PASS = False


def get_scoring_mode(scoring_policy: dict) -> str:
    """返回 scoring_mode 字段值（objective_only / mixed）。"""
    return str(scoring_policy.get("scoring_mode", DEFAULT_SCORING_MODE))


def _parse_scoring_policy(scoring_policy: dict) -> tuple[float, float, float, bool, bool]:
    """从 attempt_scoring_policy_json 解析权重与阈值。

    scoring_mode 优先级高于旧版 weight_objective / weight_manual 字段：
      - objective_only → weight_objective=1.0, weight_manual=0.0
      - mixed          → manual_score_ratio(0-100) → weight_manual=ratio/100
      - 其他/缺失      → 向后兼容，读取旧 weight_* 字段
    """
    mode = get_scoring_mode(scoring_policy)
    threshold = float(scoring_policy.get("pass_threshold", DEFAULT_PASS_THRESHOLD))
    allow_obj = bool(scoring_policy.get("allow_override_objective", DEFAULT_ALLOW_OVERRIDE_OBJECTIVE))
    allow_pass = bool(scoring_policy.get("allow_override_pass_flag", DEFAULT_ALLOW_OVERRIDE_PASS))

    if mode == "objective_only":
        w_obj, w_man = 1.0, 0.0
    elif mode == "mixed":
        ratio = float(scoring_policy.get("manual_score_ratio", 0))
        ratio = max(0.0, min(100.0, ratio))
        w_man = ratio / 100.0
        w_obj = 1.0 - w_man
    else:
        # 向后兼容：读取旧 weight_* 字段
        w_obj = float(scoring_policy.get("weight_objective", DEFAULT_WEIGHT_OBJECTIVE))
        w_man = float(scoring_policy.get("weight_manual", DEFAULT_WEIGHT_MANUAL))

    return w_obj, w_man, threshold, allow_obj, allow_pass


def calculate_final_score(
    *,
    objective_score: Optional[float],
    manual_score: Optional[float],
    scoring_policy: dict,
) -> tuple[float, bool]:
    """
    计算最终分与 pass_final。

    - 若 manual_score 缺失（None），退化为 final = objective（单分模式）。
    - 返回 (final_score, pass_final)，分数已 clamp 至 [0, 100]。
    """
    w_obj, w_man, threshold, _, _ = _parse_scoring_policy(scoring_policy)

    obj = objective_score if objective_score is not None else 0.0

    if manual_score is None:
        # 降级：只有客观分
        final = obj
        logger.info("manual_score 缺失，final_score 退化为 objective_score=%.2f", final)
    else:
        final = obj * w_obj + manual_score * w_man

    final = max(0.0, min(100.0, final))
    pass_final = final >= threshold

    return round(final, 4), pass_final


def validate_override_allowed(
    scoring_policy: dict,
    *,
    wants_override_objective: bool = False,
    wants_override_pass: bool = False,
) -> Optional[str]:
    """
    校验教师覆盖请求是否被 scoring_policy 允许。

    返回 None 表示允许；返回错误描述字符串表示禁止。
    """
    _, _, _, allow_obj, allow_pass = _parse_scoring_policy(scoring_policy)

    if wants_override_objective and not allow_obj:
        return "当前考试 scoring_policy 不允许覆盖客观分（allow_override_objective=false）"
    if wants_override_pass and not allow_pass:
        return "当前考试 scoring_policy 不允许覆盖 pass 标记（allow_override_pass_flag=false）"

    return None
