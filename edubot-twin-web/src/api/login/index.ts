import request from '@/axios'
import type { UserType } from './types'

interface RoleParams {
  roleName: string
}

export const loginApi = (data: UserType): Promise<IResponse<UserType>> => {
  return request.post({ url: '/api/v1/auth/login', data })
}

export const loginOutApi = (): Promise<IResponse> => {
  return request.get({ url: '/mock/user/loginOut' })
}

export const getUserListApi = ({ params }: AxiosConfig) => {
  return request.get<{
    code: string
    data: {
      list: UserType[]
      total: number
    }
  }>({ url: '/mock/user/list', params })
}

export const getAdminRoleApi = (
  params: RoleParams
): Promise<IResponse<AppCustomRouteRecordRaw[]>> => {
  return request.get({ url: '/mock/role/list', params })
}

export const getTestRoleApi = (params: RoleParams): Promise<IResponse<string[]>> => {
  return request.get({ url: '/mock/role/list2', params })
}

export const getUserRoutesApi = (params: { role: string }): Promise<IResponse<string[]>> => {
  return request.get({ url: '/api/v1/auth/routes', params })
}

// 获取 JWT Token
export const getTokenApi = (data: {
  username: string
  password: string
}): Promise<IResponse<{ access_token: string; token_type: string }>> => {
  return request.post({ url: '/api/v1/auth/token', data })
}

// 根据 Token 获取用户信息
export const getUserInfoByTokenApi = (token: string): Promise<IResponse<UserType>> => {
  return request.get({ url: '/api/v1/auth/me', params: { token } })
}
