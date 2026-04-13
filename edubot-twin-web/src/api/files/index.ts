// 文件管理 API 封装
//
// 提供两种使用方式：
//   1. 默认导出函数（学生服务器端工作区：/api/v1/students/files）
//   2. createFilesApiClient(base) 工厂，用于容器内 Sidecar 代理接口

import axios from 'axios'
import service from '@/axios'
import { useUserStoreWithOut } from '@/store/modules/user'
import type {
  FileListData,
  FileReadData,
  FileUploadData,
  FileSaveRequest,
  MkdirRequest,
  FileRenameRequest,
  FileMoveRequest,
  FileCopyRequest,
  BatchDeleteRequest,
  ExtractRequest,
  ExtractData,
  CompressRequest,
  CompressData
} from './types'

// API base URL 常量
export const FILES_API_BASE = '/api/v1/students/files'
export const CONTAINER_FILES_API_BASE = '/api/v1/students/container-files'
export const SHADOW_CONTAINER_FILES_API_BASE = '/api/v1/teachers/dry-run-tools/container-files'

/** 触发浏览器下载 Blob */
function triggerBlobDownload(blob: Blob, filename: string) {
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = filename
  link.click()
  URL.revokeObjectURL(link.href)
}

/**
 * 创建绑定到指定 base URL 的文件 API 客户端。
 *
 * 用于 WorkspacePanel 多模式（workspace / container / shadow-root）下
 * 统一接口、差异化端点的场景。
 */
export function createFilesApiClient(base: string) {
  const listFiles = (path = '/'): Promise<IResponse<FileListData>> => {
    return service.get({ url: `${base}/list`, params: { path } })
  }

  const readFile = (path: string): Promise<IResponse<FileReadData>> => {
    return service.get({ url: `${base}/read`, params: { path } })
  }

  const saveFile = (data: FileSaveRequest): Promise<IResponse<{ path: string; size: number }>> => {
    return service.post({ url: `${base}/save`, data })
  }

  const uploadFile = (file: File, targetPath = '/'): Promise<IResponse<FileUploadData>> => {
    const userStore = useUserStoreWithOut()
    const formData = new FormData()
    formData.append('file', file)
    formData.append('target_path', targetPath)
    return axios
      .post(`${base}/upload`, formData, {
        baseURL: import.meta.env.VITE_API_BASE_PATH,
        headers: {
          [userStore.getTokenKey ?? 'Authorization']: userStore.getToken
            ? `Bearer ${userStore.getToken}`
            : ''
        }
      })
      .then((res) => res.data)
  }

  const deleteFile = (path: string): Promise<IResponse<{ path: string }>> => {
    return service.delete({ url: `${base}/delete`, params: { path } })
  }

  const mkdir = (data: MkdirRequest): Promise<IResponse<{ path: string }>> => {
    return service.post({ url: `${base}/mkdir`, data })
  }

  const renameFile = (data: FileRenameRequest): Promise<IResponse<{ new_path: string }>> => {
    return service.post({ url: `${base}/rename`, data })
  }

  const moveFiles = (
    data: FileMoveRequest
  ): Promise<IResponse<{ success: string[]; failed: any[] }>> => {
    return service.post({ url: `${base}/move`, data })
  }

  const copyFiles = (
    data: FileCopyRequest
  ): Promise<IResponse<{ success: string[]; failed: any[] }>> => {
    return service.post({ url: `${base}/copy`, data })
  }

  const batchDeleteFiles = (
    data: BatchDeleteRequest
  ): Promise<IResponse<{ deleted: string[]; failed: any[] }>> => {
    return service.delete({ url: `${base}/batch-delete`, data })
  }

  const extractFile = (data: ExtractRequest): Promise<IResponse<ExtractData>> => {
    return service.post({ url: `${base}/extract`, data })
  }

  const compressFiles = (data: CompressRequest): Promise<IResponse<CompressData>> => {
    return service.post({ url: `${base}/compress`, data })
  }

  const downloadFile = async (
    path: string,
    token: string,
    tokenKey = 'Authorization'
  ): Promise<void> => {
    const params = new URLSearchParams({ path })
    const url = `${import.meta.env.VITE_API_BASE_PATH}${base}/download?${params}`
    const res = await fetch(url, {
      headers: { [tokenKey]: token ? `Bearer ${token}` : '' }
    })
    if (!res.ok) {
      const json = await res.json().catch(() => ({}))
      throw new Error(json?.detail ?? `下载失败 (${res.status})`)
    }
    const blob = await res.blob()
    const cd = res.headers.get('Content-Disposition') ?? ''
    const match = cd.match(/filename="?([^"\s]+)"?/)
    const filename = match?.[1] ?? path.split('/').pop() ?? 'download'
    triggerBlobDownload(blob, filename)
  }

  const downloadMultipleFiles = async (
    paths: string[],
    archiveName: string,
    token: string,
    tokenKey = 'Authorization'
  ): Promise<void> => {
    const url = `${import.meta.env.VITE_API_BASE_PATH}${base}/download-multiple`
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        [tokenKey]: token ? `Bearer ${token}` : ''
      },
      body: JSON.stringify({ paths, archive_name: archiveName })
    })
    if (!res.ok) {
      const json = await res.json().catch(() => ({}))
      throw new Error(json?.detail ?? `下载失败 (${res.status})`)
    }
    const blob = await res.blob()
    const cd = res.headers.get('Content-Disposition') ?? ''
    const match = cd.match(/filename="?([^"\s]+)"?/)
    const filename = match?.[1] ?? archiveName
    triggerBlobDownload(blob, filename)
  }

  return {
    listFiles,
    readFile,
    saveFile,
    uploadFile,
    deleteFile,
    mkdir,
    renameFile,
    moveFiles,
    copyFiles,
    batchDeleteFiles,
    extractFile,
    compressFiles,
    downloadFile,
    downloadMultipleFiles
  }
}

export type FilesApiClient = ReturnType<typeof createFilesApiClient>

// ─── 默认导出（学生服务器端工作区，保持向后兼容）─────────────────

const _defaultClient = createFilesApiClient(FILES_API_BASE)

/** 获取文件/目录列表 */
export const listFiles = (path = '.'): Promise<IResponse<FileListData>> => {
  // 服务器端工作区使用相对路径约定
  return service.get({ url: `${FILES_API_BASE}/list`, params: { path } })
}

export const readFile = _defaultClient.readFile
export const saveFile = _defaultClient.saveFile
export const uploadFile = (file: File, targetPath = '.'): Promise<IResponse<FileUploadData>> => {
  const userStore = useUserStoreWithOut()
  const formData = new FormData()
  formData.append('file', file)
  formData.append('target_path', targetPath)
  return axios
    .post(`${FILES_API_BASE}/upload`, formData, {
      baseURL: import.meta.env.VITE_API_BASE_PATH,
      headers: {
        [userStore.getTokenKey ?? 'Authorization']: userStore.getToken
          ? `Bearer ${userStore.getToken}`
          : ''
      }
    })
    .then((res) => res.data)
}
export const deleteFile = _defaultClient.deleteFile
export const mkdir = _defaultClient.mkdir
export const renameFile = _defaultClient.renameFile
export const moveFiles = _defaultClient.moveFiles
export const copyFiles = _defaultClient.copyFiles
export const batchDeleteFiles = _defaultClient.batchDeleteFiles
export const extractFile = _defaultClient.extractFile
export const compressFiles = _defaultClient.compressFiles
export const downloadFile = _defaultClient.downloadFile
export const downloadMultipleFiles = _defaultClient.downloadMultipleFiles
