/**
 * useFileOperations — 统一文件操作 Composable
 *
 * 接收 `apiPrefix` 参数（Ref<string>），适配三种后端：
 *   - 学生端文件：      '/api/v1/students/files'
 *   - 教师文件包：       '/api/v1/teachers/file-bundles/123/files'
 *   - 教师环境包：       '/api/v1/teachers/env-bundles/456/files'
 *
 * 所有文件操作（列表、读取、保存、上传、删除）通过同一接口调用，
 * 由调用方传入正确的 apiPrefix 即可切换目标后端。
 */
import request from '@/axios'
import type {
  BundleFileItem,
  BundleFileListResponse,
  BundleFileReadResponse
} from '@/api/experiment/types'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ref, type Ref } from 'vue'

export interface FileOperationOptions {
  /** protected paths that cannot be deleted (e.g., 'startup.sh') */
  protectedPaths?: string[]
}

export function useFileOperations(apiPrefix: Ref<string>, options: FileOperationOptions = {}) {
  const fileList = ref<BundleFileItem[]>([])
  const currentPath = ref<string>('')
  const fileContent = ref<string>('')
  const fileContentModifiedAt = ref<string | undefined>(undefined)
  const openedFilePath = ref<string | undefined>(undefined)
  const hasUnsavedChanges = ref(false)
  const loading = ref(false)

  // ─── 列出文件 ────────────────────────────────────────────────────────────────

  const listFiles = async (path?: string): Promise<void> => {
    loading.value = true
    try {
      const res = await request.get<BundleFileListResponse>({
        url: apiPrefix.value,
        params: path ? { path } : undefined
      })
      fileList.value = res.data?.items ?? []
      currentPath.value = path ?? ''
    } catch (e) {
      ElMessage.error('获取文件列表失败')
    } finally {
      loading.value = false
    }
  }

  // ─── 读取文件 ────────────────────────────────────────────────────────────────

  const readFile = async (path: string): Promise<void> => {
    loading.value = true
    try {
      const res = await request.get<BundleFileReadResponse>({
        url: `${apiPrefix.value}/read`,
        params: { path }
      })
      fileContent.value = res.data?.content ?? ''
      fileContentModifiedAt.value = res.data?.modified_at
      openedFilePath.value = path
      hasUnsavedChanges.value = false
    } catch (e: any) {
      ElMessage.error('读取文件失败：' + (e?.response?.data?.detail || '未知错误'))
    } finally {
      loading.value = false
    }
  }

  // ─── 保存文件 ────────────────────────────────────────────────────────────────

  const saveFile = async (path: string, content: string): Promise<boolean> => {
    try {
      await request.post({
        url: `${apiPrefix.value}/save`,
        data: { path, content }
      })
      hasUnsavedChanges.value = false
      ElMessage.success('保存成功')
      return true
    } catch (e: any) {
      const errCode = e?.response?.data?.detail
      if (errCode === 'FILE_SAVE_CONFLICT') {
        ElMessage.error('文件已被其他操作更新，请刷新后重试')
      } else {
        ElMessage.error('保存失败：' + (e?.response?.data?.detail || '未知错误'))
      }
      return false
    }
  }

  // ─── 上传文件 ────────────────────────────────────────────────────────────────

  const uploadFile = async (file: File): Promise<void> => {
    const formData = new FormData()
    formData.append('file', file)
    try {
      await request.post({
        url: `${apiPrefix.value}/upload`,
        data: formData,
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      ElMessage.success(`"${file.name}" 上传成功`)
      await listFiles(currentPath.value || undefined)
    } catch (e: any) {
      const status = e?.response?.status
      if (status === 413) {
        ElMessage.error('文件超过 200MB 限制，请减小文件包体积')
      } else {
        ElMessage.error('上传失败：' + (e?.response?.data?.detail || '未知错误'))
      }
    }
  }

  // ─── 删除文件 ────────────────────────────────────────────────────────────────

  const deleteFile = async (path: string): Promise<void> => {
    const filename = path.split('/').pop() ?? path
    if (options.protectedPaths?.includes(filename)) {
      ElMessage.warning('启动脚本不可删除')
      return
    }

    await ElMessageBox.confirm(`确认删除 "${filename}" 吗？此操作不可撤销。`, '删除确认', {
      confirmButtonText: '确认删除',
      cancelButtonText: '取消',
      type: 'warning'
    })

    try {
      await request.delete({
        url: `${apiPrefix.value}/delete`,
        params: { path }
      })
      ElMessage.success('删除成功')

      // 如果删除的是当前打开的文件，清空编辑器
      if (openedFilePath.value === path) {
        openedFilePath.value = undefined
        fileContent.value = ''
        hasUnsavedChanges.value = false
      }

      await listFiles(currentPath.value || undefined)
    } catch (e: any) {
      const errCode = e?.response?.data?.detail
      if (errCode === 'STARTUP_SCRIPT_PROTECTED') {
        ElMessage.error('启动脚本不可删除')
      } else {
        ElMessage.error('删除失败：' + (e?.response?.data?.detail || '未知错误'))
      }
    }
  }

  // ─── 离开前确认 ───────────────────────────────────────────────────────────────

  /**
   * 有未保存变更时询问用户，返回是否可以继续（true=已保存/放弃，false=取消）
   */
  const confirmLeave = async (): Promise<boolean> => {
    if (!hasUnsavedChanges.value) return true

    try {
      const action = await ElMessageBox.confirm('当前有未保存的修改，请选择操作：', '提示', {
        confirmButtonText: '保存后继续',
        cancelButtonText: '放弃修改',
        distinguishCancelAndClose: true,
        type: 'warning'
      })
      if (action === 'confirm' && openedFilePath.value) {
        const ok = await saveFile(openedFilePath.value, fileContent.value)
        return ok
      }
      return true
    } catch (action) {
      // 'cancel' = 放弃修改，'close' = 关闭弹窗取消操作
      if (action === 'cancel') {
        hasUnsavedChanges.value = false
        return true
      }
      return false
    }
  }

  return {
    fileList,
    currentPath,
    fileContent,
    fileContentModifiedAt,
    openedFilePath,
    hasUnsavedChanges,
    loading,
    listFiles,
    readFile,
    saveFile,
    uploadFile,
    deleteFile,
    confirmLeave
  }
}
