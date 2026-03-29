// 文件管理 API 封装
// 基于项目约定的 service（非 axios 直调）

import axios from 'axios'
import service from '@/axios'
import { useUserStoreWithOut } from '@/store/modules/user'
import type {
  FileListData,
  FileReadData,
  FileUploadData,
  FileSaveRequest,
  MkdirRequest
} from './types'

const BASE = '/api/v1/students/files'

/** 获取文件/目录列表 */
export const listFiles = (path = '.'): Promise<IResponse<FileListData>> => {
  return service.get({ url: `${BASE}/list`, params: { path } })
}

/** 读取文件内容 */
export const readFile = (path: string): Promise<IResponse<FileReadData>> => {
  return service.get({ url: `${BASE}/read`, params: { path } })
}

/** 保存文件内容 */
export const saveFile = (
  data: FileSaveRequest
): Promise<IResponse<{ path: string; size: number }>> => {
  return service.post({ url: `${BASE}/save`, data })
}

/**
 * 上传文件
 *
 * 注意：不使用 service 封装，直接用 axios 原生发送 FormData。
 * 原因：service 封装会硬设 Content-Type: application/json，
 *      而 multipart/form-data 的 boundary 必须由 axios 自动生成，
 *      手动覆盖 Content-Type 会导致后端 422 Field required 错误。
 */
export const uploadFile = (file: File, targetPath = '.'): Promise<IResponse<FileUploadData>> => {
  const userStore = useUserStoreWithOut()
  const formData = new FormData()
  formData.append('file', file)
  formData.append('target_path', targetPath)

  return axios
    .post(`${BASE}/upload`, formData, {
      baseURL: import.meta.env.VITE_API_BASE_PATH,
      headers: {
        [userStore.getTokenKey ?? 'Authorization']: userStore.getToken
          ? `Bearer ${userStore.getToken}`
          : ''
        // 不设置 Content-Type，让 axios 自动补 multipart/form-data; boundary=...
      }
    })
    .then((res) => res.data)
}

/** 删除文件或目录 */
export const deleteFile = (path: string): Promise<IResponse<{ path: string }>> => {
  return service.delete({ url: `${BASE}/delete`, params: { path } })
}

/** 创建目录 */
export const mkdir = (data: MkdirRequest): Promise<IResponse<{ path: string }>> => {
  return service.post({ url: `${BASE}/mkdir`, data })
}
