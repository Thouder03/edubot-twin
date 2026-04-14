/**
 * useContainerStart - 容器启动标准流程（12期补充：统一仿真与考试启动）
 *
 * 导出：
 *   STAGE_TEXT_MAP           任务阶段文案映射（SDD §15.1）
 *   pollTaskUntilDone        轮询 task 直到 SUCCEEDED / FAILED
 *   ensureContainerRunning   确保容器处于 running 状态（Simulation.vue 内部重启专用）
 *   ContainerStartMode       启动模式类型
 *   ContainerStartOptions    启动参数接口
 *   startContainerUnified    统一容器启动流程（处理模式冲突 + 容器创建 + 文件分发）
 */
import { ElLoading, ElMessageBox } from 'element-plus'
import request from '@/axios'
import { getMyContainerApi, startMyContainerApi } from '@/api/container'
import { getSimulationTaskApi, startSimulationApi, distributeSimulationFilesApi } from '@/api/experiment'
import { startExamContainerApi } from '@/api/exam/attempts'
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

// ─── Task 轮询 ────────────────────────────────────────────────────────────────

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

// ─── 容器状态轮询（Simulation.vue 内部重启专用）──────────────────────────────

/**
 * 确保容器处于 running 状态（Simulation.vue 内部心跳超时后的自动重启场景）。
 *
 * 不适用于初始启动（初始启动请使用 startContainerUnified）。
 *
 * @returns true 表示容器已就绪，false 表示无法启动
 */
export async function ensureContainerRunning(
  loadingInstance: LoadingInstance,
  maxPolls = 30,
  intervalMs = 2000
): Promise<boolean> {
  let status: string | null = null
  try {
    const res = await getMyContainerApi()
    status = res?.data?.status ?? null
  } catch {
    return false
  }

  if (status === 'running') return true

  if (status === 'stopped') {
    loadingInstance.setText('正在启动仿真容器...')
    await startMyContainerApi()
  } else if (status === 'creating') {
    loadingInstance.setText('仿真容器启动中，请稍候...')
  } else {
    return false
  }

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

// ─── 统一容器启动流程（12期补充）─────────────────────────────────────────────

/** 启动模式 */
export type ContainerStartMode = 'simulation' | 'exam'

/** 统一启动参数 */
export interface ContainerStartOptions {
  mode: ContainerStartMode
  /** 仿真模式必填 */
  versionId?: number
  /** 考试模式必填 */
  examId?: number
}

/**
 * 检测容器模式冲突。
 *
 * - 容器未处于活跃状态（running/creating）：不弹窗
 * - 同模式（实验→实验、考试→考试）：不弹窗，由后端处理复用或重建
 * - 跨模式且容器活跃：弹出确认对话框
 *
 * @returns 'no_conflict' | 'confirmed' | 'cancelled'
 */
async function checkModeConflict(
  currentPurpose: string | null | undefined,
  currentStatus: string | null | undefined,
  targetMode: ContainerStartMode
): Promise<'no_conflict' | 'confirmed' | 'cancelled'> {
  // 容器不存在或未处于活跃状态，无需弹窗
  if (!currentPurpose) return 'no_conflict'
  if (currentStatus !== 'running' && currentStatus !== 'creating') return 'no_conflict'

  const isCurrentExam = currentPurpose.startsWith('考试：')
  const isCurrentSimulation = currentPurpose.startsWith('实验：')

  if (targetMode === 'exam' && isCurrentExam) return 'no_conflict'
  if (targetMode === 'simulation' && isCurrentSimulation) return 'no_conflict'

  const currentLabel = isCurrentExam
    ? `考试容器（${currentPurpose}）`
    : `实验容器（${currentPurpose}）`
  const targetLabel = targetMode === 'exam' ? '考试' : '实验'

  try {
    await ElMessageBox.confirm(
      `当前正在运行${currentLabel}。\n启动${targetLabel}容器将关闭当前容器，是否继续？`,
      '容器模式冲突',
      {
        confirmButtonText: '确定，关闭当前容器',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    return 'confirmed'
  } catch {
    return 'cancelled'
  }
}

/** 仿真模式内部启动流程 */
async function _startSimulation(versionId: number, loading: LoadingInstance): Promise<boolean> {
  const startRes = await startSimulationApi({ version_id: versionId })
  const startData = startRes.data

  if (startData?.task_id) {
    loading.setText('正在准备配置...')
    const task = await pollTaskUntilDone(startData.task_id, loading)
    if (task.task_status === 'FAILED') {
      return false
    }
  }

  loading.setText('正在分发实验文件...')
  const distRes = await distributeSimulationFilesApi({
    version_id: versionId,
    selected_paths: [],
    mode: 'pull'
  })
  const distData = distRes.data
  if (distData?.task_id) {
    const distTask = await pollTaskUntilDone(distData.task_id, loading)
    if (distTask.task_status === 'FAILED') {
      return false
    }
  }

  return true
}

/** 考试模式内部启动流程 */
async function _startExamContainer(examId: number, loading: LoadingInstance): Promise<boolean> {
  const startRes = await startExamContainerApi({ exam_id: examId })
  const taskId = startRes.data?.task_id

  if (taskId) {
    loading.setText('正在创建考试容器，大概需要 30 秒...')
    const task = await pollTaskUntilDone(taskId, loading)
    if (task.task_status === 'FAILED') {
      return false
    }
  }

  loading.setText('正在分发考试文件...')
  await request.post({
    url: '/api/v1/students/simulation/distribute-exam-files',
    data: { exam_id: examId }
  })

  return true
}

/**
 * 统一容器启动流程（处理模式冲突 + 容器创建 + 健康检查 + 文件分发）。
 *
 * 流程：
 *   1. 查询当前容器状态与用途
 *   2. 跨模式冲突检测 → 弹出确认对话框
 *   3. 按模式调用对应启动 API（仿真/考试）
 *   4. 轮询任务进度
 *   5. 调用对应文件分发 API
 *
 * @returns true 表示容器已就绪，false 表示用户取消或启动失败
 */
export async function startContainerUnified(
  options: ContainerStartOptions,
  loadingInstance: LoadingInstance
): Promise<boolean> {
  // 1. 查询当前容器用途与状态
  loadingInstance.setText('正在检查容器状态...')
  let currentPurpose: string | null | undefined
  let currentStatus: string | null | undefined
  try {
    const res = await getMyContainerApi()
    currentPurpose = res?.data?.purpose
    currentStatus = res?.data?.status
  } catch {
    // 404 = 无容器，继续
  }

  // 2. 模式冲突检测
  const conflict = await checkModeConflict(currentPurpose, currentStatus, options.mode)
  if (conflict === 'cancelled') return false

  // 3. 按模式分发启动逻辑
  if (options.mode === 'simulation') {
    return await _startSimulation(options.versionId!, loadingInstance)
  } else {
    return await _startExamContainer(options.examId!, loadingInstance)
  }
}
