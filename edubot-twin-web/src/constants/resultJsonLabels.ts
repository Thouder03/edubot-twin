/**
 * result.json 固定字段名 → 中文显示名映射（第16期）
 *
 * 设计原则：
 * - 由平台规范定义的固定字段使用中文名
 * - custom_fields / 未识别的 metrics 字段原样展示（不在此 Map 中）
 * - 维护在前端常量，不通过接口动态获取，避免不必要的后端依赖
 */

export const RESULT_JSON_FIELD_LABELS: Record<string, string> = {
  status: '评测状态',
  objective_score: '客观分',
  pass: '是否通过',
  summary: '评测评语'
}

/**
 * metrics 子字段中文名映射
 */
export const RESULT_JSON_METRICS_LABELS: Record<string, string> = {
  elapsed_seconds: '运行时长（秒）',
  goal_reached: '到达目标',
  collision_count: '碰撞次数',
  path_length: '路径长度'
}

/**
 * 获取字段的中文显示名（先查顶层字段，再查 metrics 子字段，找不到则返回原键名）
 */
export function getFieldLabel(key: string, inMetrics = false): string {
  if (inMetrics) {
    return RESULT_JSON_METRICS_LABELS[key] ?? key
  }
  return RESULT_JSON_FIELD_LABELS[key] ?? key
}
