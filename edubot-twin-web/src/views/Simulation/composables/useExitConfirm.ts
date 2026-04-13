/**
 * useExitConfirm - 退出仿真/考试时的二次确认对话框
 *
 * 提供"临时退出"与"暂停容器后退出"两种选项，
 * 供 SimulationHeader 和 ExamHeader 共用。
 */
import { ElMessageBox, ElMessage, ElLoading } from 'element-plus'
import { stopMyContainerApi, heartbeatApi } from '@/api/container'

const TEMP_EXIT_DESTROY_SECONDS = 120

type ExitMode = 'temporary' | 'stopAndExit'

/**
 * 弹出退出确认对话框，并处理两种退出策略。
 *
 * @param onBack - 退出后的回调，参数为退出模式
 * @param title  - 对话框标题，默认"退出确认"
 */
export async function confirmExit(
  onBack: (mode: ExitMode) => void,
  title = '退出确认'
): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `请选择退出方式：\n\n- 临时退出：保持容器运行，约 ${TEMP_EXIT_DESTROY_SECONDS} 秒无心跳后自动销毁\n- 暂停容器后退出：等待容器停止完成再离开`,
      title,
      {
        confirmButtonText: '暂停容器后退出（等待）',
        cancelButtonText: `临时退出（${TEMP_EXIT_DESTROY_SECONDS} 秒后自动销毁）`,
        type: 'warning',
        distinguishCancelAndClose: true,
        closeOnClickModal: true,
        closeOnPressEscape: true
      }
    )
    const loading = ElLoading.service({ text: '正在暂停容器，请稍候...' })
    try {
      await stopMyContainerApi()
      onBack('stopAndExit')
    } finally {
      loading.close()
    }
  } catch (action) {
    if (action === 'cancel') {
      try {
        await heartbeatApi()
      } catch {
        // 网络异常不阻断临时退出
      }
      ElMessage.info(`已临时退出，若 ${TEMP_EXIT_DESTROY_SECONDS} 秒内未恢复心跳，容器将自动销毁`)
      onBack('temporary')
    }
    // action === 'close' 时视为取消，不执行退出
  }
}
