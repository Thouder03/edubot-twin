# 前后端 API 接口分析与规范文档

## 1. 概览 (Overview)

本项目目前处于混合开发阶段，部分核心 API (认证、学生管理) 已对接后端 FastAPI 实现，而大部分业务功能 (仪表盘、部门、角色等) 仍使用 Mock 数据。

本文档详细列出了现有的前端 API 调用及其对应的后端状态（已实现或需实现），并规范了后端应返回的数据格式。

---

## 2. 已对接后端 API (Real APIs)

以下接口已在后端 `edubot-twin-server` 中实现，前端应直接调用 `/api/v1/...`。

### 2.1 认证模块 (Authentication)

- **后端文件**: `app/api/v1/endpoints/common/auth.py`
- **Schema 定义**: `app/schemas/auth.py`

| 前端方法      | URL                   | HTTP 方法 | 后端状态  | 描述                     |
| :------------ | :-------------------- | :-------- | :-------- | :----------------------- |
| `loginApi`    | `/api/v1/auth/login`  | POST      | ✅ 已实现 | 用户登录 (支持学生/教师) |
| `loginOutApi` | `/mock/user/loginOut` | GET       | ❌ Mock   | 退出登录 (需后端实现)    |

#### 登录接口响应格式 (Login Response)

后端返回结构 (`LoginResponse`):

```json
{
  "code": 0,
  "data": {
    "username": "student1",
    "role": "student", // 或 "admin"
    "roleId": "3" // 对应: 1=admin, 2=test, 3=student
  }
}
```

> **注意**:
>
> 1. 目前前端 `loginOutApi` 仍指向 mock，建议后续对接 `/api/v1/auth/logout` (需实现)。
> 2. `getUserListApi` 等目前均为 mock。

### 2.2 学生管理模块 (Student Management)

- **后端文件**: `app/api/v1/endpoints/student/basic.py`
- **Schema 定义**: `app/schemas/student.py`

| URL                     | HTTP 方法 | 后端状态  | 描述                |
| :---------------------- | :-------- | :-------- | :------------------ |
| `/api/v1/students/`     | GET       | ✅ 已实现 | 获取学生列表 (分页) |
| `/api/v1/students/{id}` | GET       | ✅ 已实现 | 获取单个学生详情    |
| `/api/v1/students/`     | POST      | ✅ 已实现 | 创建学生            |
| `/api/v1/students/{id}` | PUT       | ✅ 已实现 | 更新学生信息        |
| `/api/v1/students/{id}` | DELETE    | ✅ 已实现 | 删除学生            |

#### 学生信息响应格式 (Student Response)

后端返回结构 (`StudentResponse`):

```json
{
  "id": 1,
  "username": "2023001",
  "real_name": "张三",
  "email": "zhangsan@example.com",
  "is_active": true,
  "created_at": "2023-10-01T10:00:00",
  "updated_at": "2023-10-01T10:00:00"
}
```

---

## 3. 待实现后端 API (Mock APIs)

以下接口目前在前端使用 `/mock/...` 路径，**无需立即修改前端代码**，但后端需按照下列格式开发接口，未来进行替换。

### 3.1 学生首页数据 (Student Home)

- **前端文件**: `src/api/student/index.ts`
- **当前调用**: `getStudentHomeDataApi` -> `/mock/student/home`
- **建议后端**: `app/api/v1/endpoints/student/stats.py`

#### 期望后端响应格式

```json
{
  "code": 0,
  "data": {
    "pendingExams": 3, // 待完成考试数量
    "unreadMessages": 5 // 未读消息数量
  }
}
```

### 3.2 仪表盘模块 (Dashboard)

- **前端文件**: `src/api/dashboard/...`
- **建议后端**: `app/api/v1/endpoints/common/dashboard.py`

| 前端方法                 | 当前 Mock URL                     | 描述         | 期望数据结构                                         |
| :----------------------- | :-------------------------------- | :----------- | :--------------------------------------------------- |
| `getCountApi`            | `/mock/analysis/total`            | 分析页统计   | `[ { "id": 1, "value": 1000, "total": 2000 }, ... ]` |
| `getUserAccessSourceApi` | `/mock/analysis/userAccessSource` | 用户来源分析 | `[ { "value": 1000, "name": "Direct" }, ... ]`       |
| `getWorkplaceTotalApi`   | `/mock/workplace/total`           | 工作台统计   | `{ "project": 10, "access": 20, "todo": 5 }`         |

### 3.3 部门与组织 (Department)

- **前端文件**: `src/api/department/index.ts`
- **当前 Mock URL**: `/mock/department/...`

需要后端实现部门的增删改查及部门成员管理。

### 3.4 菜单与权限 (Menu & Role)

- **前端文件**: `src/api/menu/index.ts`, `src/api/role/index.ts`
- **当前 Mock URL**: `/mock/menu/list`, `/mock/role/list`

后端需要提供基于角色的动态路由数据。

#### 期望菜单响应格式

```json
{
  "code": 0,
  "data": [
    {
      "path": "/dashboard",
      "component": "LAYOUT",
      "meta": { "title": "Dashboard" },
      "children": [...]
    }
  ]
}
```

### 3.5 通用与字典 (Common)

- **前端文件**: `src/api/common/index.ts`
- **当前 Mock URL**: `/mock/dict/list`

需实现通用字典接口，用于前端下拉框选项。

---

## 4. 后端开发建议 (Backend Implementation Recommendations)

1.  **优先实现 `loginOutApi`**: 虽然简单，但是完整的认证流程闭环。
2.  **实现 `getStudentHomeDataApi`**: 这是一个简单的聚合接口，只需查询考试表和消息表的 count。
3.  **统一响应结构**:
    确保所有非 Pydantic 自动生成的接口（如自定义聚合数据）都遵循 `{ "code": 0, "data": ... }` 的标准结构，或者在 Axios 拦截器中统一处理 Pydantic 的直接返回（目前 Pydantic 默认直接返回 data，前端 Axios 可能需要适配）。

    _注: 目前 `common/auth.py` 中的 `LoginResponse` 显式包含了 `code` 字段，这与 Mock 数据结构一致。建议所有自定义接口都保持这一规范。_
