export interface UserLoginType {
  username: string
  // password 字段已移除，改用 Token 方式记住登录状态
}

export interface UserType {
  username: string
  password: string
  role: string
  roleId: string
}
