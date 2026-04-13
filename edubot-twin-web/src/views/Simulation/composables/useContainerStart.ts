/**
 * useContainerStart - 仿真容器启动标准流程
 *
 * 导出：
 *   STAGE_TEXT_MAP        任务阶段文案映射（SDD §15.1）
 *   pollTaskUntilDone     轮询 task 直到 SUCCEEDED / FAILED
 *                         （用于 startSimulationApi / distributeSimulationFilesApi）
 *   ensureContainerRunning 确保容器处于 running 状态（考试模式，无需 version_id）
 */
import { ElLoading } from 'element-plus'
import { getMyContainerApi, startMyContainerApi } from '@/api/container'
import { getSimulationTaskApi } from '@/api/experiment'
import type { StudentSimulationTaskResponse } from '@/api/experiment/types'

// ─── 阶段文案映射（SDD §15.1）────────────────────────────────────────────────

export const STAGE_TEXT_MAP: Record<string, string> = {
  PREPARING_CONFIG: '正在准备配置...',
  STOPPING_OLD_CONTAINER: '正在清理旧环境...',
  CREATING_NEW_CONTAINER: '正在创建仿真容器...',
  CHECKING_GZWEB: '等待 Gazebo 仿真引擎启动...',
  CHECKING_ROSBRIDGE: '等待 ROS 通信桥启动...',
  VALIDATING_MANIFEST: '正在校验实验文件清单...',
  DISTRIBUTING_FILES: '正在分发实验文件到容器...',
  SETTING_PERMISSIONS: '正在设置实验目录权限...',
  SUCCEEDED: '仿真环境就绪，正在打开...',
  FAILED: '启动失败'
}

type LoadingInstance = ReturnType<typeof ElLoading.service>

// ─── Task 轮询（用于 startSimulationApi / distributeSimulationFilesApi）────────

/**
 * 轮询任务直到 SUCCEEDED / FAILED（最多 90 轮，每轮 2s）。
 * 按 current_stage 动态更新 loading 文案。
 *
 * @throws Error 当任务为空或超时
 */
export async function pollTaskUntilDone(
  taskId: string,
  loadingInstance: LoadingInstance
): Promise<StudentSimulationTaskResponse> {
  const maxRounds = 90
  const intervalMs = 2000

  for (let i = 0; i < maxRounds; i++) {
    const res = await getSimulationTaskApi(taskId)
    const task = res.data
    if (!task) throw new Error('task response empty')

    const stage = (task as any).current_stage as string | undefined
    if (stage && STAGE_TEXT_MAP[stage]) {
      loadingInstance.setText(STAGE_TEXT_MAP[stage])
    }

    if (task.task_status === 'SUCCEEDED' || task.task_status === 'FAILED') return task

    await new Promise((resolve) => setTimeout(resolve, intervalMs))
  }

  throw new Error('task timeout')
}

// ─── 容器状态轮询（考试模式，基于 /mine 状态接口）────────────────────────────

/**
 * 确保容器处于 running 状态（考试模式专用，无需 version_id）。
 *
 * 状态处理策略：
 *   running  → 直接返回 true
 *   stopped  → 调用 startMyContainerApi 后轮询
 *   creating → 等待轮询
 *   其他     → 返回 false（调用方负责展示错误）
 *   无容器   → 返回 false（调用方提示联系管理员）
 *
 * @returns true 表示容器已就绪，false 表示无法启动
 */
export async function ensureContainerRunning(
  loadingInstance: LoadingInstance,
  maxPolls = 30,
  intervalMs = 2000
): Promise<boolean> {
  // 1. 查询当前状态
  let status: string | null = null
  try {
    const res = await getMyContainerApi()
    status = res?.data?.status ?? null
  } catch (err: any) {
    // 404 → 未分配容器
    return false
  }

  if (status === 'running') return true

  if (status === 'stopped') {
    loadingInstance.setText('正在启动仿真容器...')
    await startMyContainerApi()
    // 继续走轮询
  } else if (status === 'creating') {
    loadingInstance.setText('仿真容器启动中，请稍候...')
    // 直接走轮询
  } else {
    // error / stopping / removing / null
    return false
  }

  // 2. 轮询直到 running 或失败
  for (let i = 0; i < maxPolls; i++) {
    await new Promise((resolve) => setTimeout(resolve, intervalMs))
    try {
      const res = await getMyContainerApi()
      const s = res?.data?.status
      if (s === 'running') return true
      if (s === 'error') return false
      if (s === 'creating') loadingInstance.setText('仿真容器启动中，请稍候...')
    } catch {
      // 网络抖动，继续重试
    }
  }
  return false
}
