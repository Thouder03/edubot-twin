// 学生首页数据类型定义
export interface StudentHomeData {
  pendingExams: number // 待完成考试数量
  unreadMessages: number // 未读消息数量
}

export interface StudentItem {
  id: number
  username: string
  real_name: string
  email?: string
  is_active: boolean
  created_at: string
}

export interface StudentCreate {
  username: string
  password: string
  real_name: string
  email?: string
}

export interface StudentUpdate {
  username?: string
  password?: string
  real_name?: string
  email?: string
  is_active?: boolean
}
