import type { ContainerStatus } from '@/api/container/types'

export const CONTAINER_STATUS_TEXT_MAP: Record<ContainerStatus, string> = {
  running: '运行中',
  stopping: '容器正在停止，请稍候...',
  stopped: '容器已停止，请返回首页重启后使用',
  creating: '容器启动中，请稍候...',
  removing: '容器删除中',
  error: '容器异常，请联系管理员'
}

export function getContainerStatusText(status: ContainerStatus | null | undefined): string {
  if (!status) return '容器状态未知，请稍候...'
  return CONTAINER_STATUS_TEXT_MAP[status] ?? status
}
