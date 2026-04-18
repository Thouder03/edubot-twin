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
