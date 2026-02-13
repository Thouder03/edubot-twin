# Edubot Twin Server - 后端 API

数字孪生机器人实训平台的后端服务,提供学生和教师管理的 RESTful API。

## 🚀 技术栈

- **框架**: FastAPI 0.115.0 (高性能异步 Web 框架)
- **ORM**: SQLAlchemy 2.0+ (异步模式)
- **数据库**: SQLite (开发环境,可切换至 PostgreSQL)
- **数据验证**: Pydantic V2
- **密码加密**: bcrypt
- **服务器**: Uvicorn (ASGI 服务器)

## 📦 安装依赖

```bash
# 确保使用项目根目录的虚拟环境
cd /home/ubuntu20/code/edubot-twin/edubot-twin-server

# 安装依赖
../.venv/bin/pip install -r requirements.txt
```

## 🗄️ 数据库初始化

首次运行前需要初始化数据库:

```bash
../.venv/bin/python init_db.py
```

该脚本会:

- 创建 `edubot.db` SQLite 数据库文件
- 创建 `students` 表
- 插入 4 个示例学生数据 (用户名: student001-004, 密码: 123456)

## 🏃 运行开发服务器

```bash
../.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

服务器启动后访问:

- **API 文档 (Swagger UI)**: http://localhost:8000/docs
- **API 文档 (ReDoc)**: http://localhost:8000/redoc
- **健康检查**: http://localhost:8000/api/v1/health

## 📚 API 端点

### 学生管理 (`/api/v1/students`)

| 方法   | 路径                    | 功能                | 请求体          |
| ------ | ----------------------- | ------------------- | --------------- |
| GET    | `/api/v1/students`      | 获取学生列表 (分页) | -               |
| GET    | `/api/v1/students/{id}` | 获取单个学生        | -               |
| POST   | `/api/v1/students`      | 创建学生            | `StudentCreate` |
| PUT    | `/api/v1/students/{id}` | 更新学生            | `StudentUpdate` |
| DELETE | `/api/v1/students/{id}` | 删除学生            | -               |

### 学生数据结构

**StudentCreate** (创建学生)

```json
{
  "username": "student001",
  "password": "123456",
  "real_name": "张三",
  "email": "zhangsan@example.com"
}
```

**StudentUpdate** (更新学生,所有字段可选)

```json
{
  "real_name": "李四",
  "email": "lisi@example.com",
  "password": "newpassword",
  "is_active": true
}
```

**StudentResponse** (响应模型,不含密码)

```json
{
  "id": 1,
  "username": "student001",
  "real_name": "张三",
  "email": "zhangsan@example.com",
  "is_active": true,
  "created_at": "2026-02-07T11:24:23.802824",
  "updated_at": "2026-02-07T11:24:23.802827"
}
```

## 🧪 API 测试示例

### 获取学生列表

```bash
curl http://localhost:8000/api/v1/students
```

### 获取单个学生

```bash
curl http://localhost:8000/api/v1/students/1
```

### 创建学生

```bash
curl -X POST http://localhost:8000/api/v1/students \
  -H "Content-Type: application/json" \
  -d '{
    "username": "newstudent",
    "password": "123456",
    "real_name": "新学生",
    "email": "new@example.com"
  }'
```

### 更新学生

```bash
curl -X PUT http://localhost:8000/api/v1/students/1 \
  -H "Content-Type: application/json" \
  -d '{"real_name": "更新后的姓名"}'
```

### 删除学生

```bash
curl -X DELETE http://localhost:8000/api/v1/students/1
```

## 📁 项目结构

```
edubot-twin-server/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI 主应用
│   ├── api/
│   │   └── v1/
│   │       ├── api.py             # 路由聚合
│   │       └── endpoints/
│   │           ├── student/       # 学生模块 (模块化架构)
│   │           │   ├── __init__.py
│   │           │   ├── basic.py   # 基本 CRUD
│   │           │   └── ...        # 其他子模块 (待扩展)
│   │           ├── teacher/       # 教师模块
│   │           │   └── __init__.py
│   │           └── common/        # 公共功能
│   │               └── __init__.py
│   ├── crud/
│   │   └── student.py             # 学生 CRUD 操作
│   ├── db/
│   │   ├── base.py                # SQLAlchemy 基类
│   │   └── database.py            # 异步数据库配置
│   ├── models/
│   │   └── student.py             # 学生 ORM 模型
│   └── schemas/
│       └── student.py             # Pydantic Schema
├── init_db.py                     # 数据库初始化脚本
├── requirements.txt               # Python 依赖
├── .gitignore                     # Git 忽略规则
├── edubot.db                      # SQLite 数据库文件
├── README.md                      # 项目文档
└── API_ARCHITECTURE.md            # API 架构设计文档
```

> [!NOTE]
> **架构升级**: 已采用模块化架构,按角色和功能拆分 API 端点。详见 [API_ARCHITECTURE.md](./API_ARCHITECTURE.md)。

## 🗃️ 数据库表结构

### students 表

| 字段名        | 类型         | 约束                   | 说明              |
| ------------- | ------------ | ---------------------- | ----------------- |
| id            | INTEGER      | PRIMARY KEY            | 主键 (自增)       |
| username      | VARCHAR(50)  | UNIQUE, NOT NULL       | 学号/用户名       |
| password_hash | VARCHAR(255) | NOT NULL               | 密码哈希 (bcrypt) |
| real_name     | VARCHAR(50)  | NULL                   | 真实姓名          |
| email         | VARCHAR(100) | UNIQUE, NULL           | 邮箱              |
| is_active     | BOOLEAN      | NOT NULL, DEFAULT TRUE | 账号激活状态      |
| created_at    | DATETIME     | NOT NULL               | 创建时间          |
| updated_at    | DATETIME     | NOT NULL               | 更新时间          |

## 🔐 安全特性

- ✅ 密码使用 bcrypt 哈希存储
- ✅ API 响应自动过滤 `password_hash` 字段
- ✅ Pydantic 自动验证输入数据 (邮箱格式、字符串长度等)
- ✅ CORS 配置限制前端跨域访问

## 🛠️ 开发指南

### 添加新字段到学生模型

1. 修改 `app/models/student.py` 添加字段
2. 修改 `app/schemas/student.py` 的相关 Schema
3. 删除 `edubot.db` 并重新运行 `init_db.py`

后续可集成 Alembic 进行数据库迁移。

### 添加教师 API

项目已预留教师 API 扩展接口,只需:

1. 创建 `app/models/teacher.py` (ORM 模型)
2. 创建 `app/schemas/teacher.py` (Pydantic Schema)
3. 创建 `app/crud/teacher.py` (CRUD 操作)
4. 创建 `app/api/v1/endpoints/teacher.py` (API 端点)
5. 在 `app/api/v1/api.py` 中取消注释教师路由

### 切换到 PostgreSQL

修改 `app/db/database.py`:

```python
# 替换 DATABASE_URL
DATABASE_URL = "postgresql+asyncpg://user:password@localhost/edubot_db"

# 安装依赖
pip install asyncpg
```

## 🐛 常见问题

### 1. 数据库文件被锁定

**错误**: `database is locked`

**解决**: 确保只有一个进程在访问数据库,关闭其他运行中的服务器实例。

### 2. 模块导入错误

**错误**: `ModuleNotFoundError: No module named 'app'`

**解决**: 确保从 `edubot-twin-server` 目录运行命令,而不是 `app` 目录。

### 3. 虚拟环境路径错误

**错误**: `.venv/bin/python: 没有那个文件或目录`

**解决**: 虚拟环境在父目录,使用 `../.venv/bin/python`。

## 🔗 前后端联调

### 前端配置

前端已配置对接后端登录接口:

**文件**: `edubot-twin-web/src/api/login/index.ts`

```typescript
export const loginApi = (data: UserType): Promise<IResponse<UserType>> => {
  return request.post({ url: "/api/v1/auth/login", data });
};
```

### 联调步骤

1. **启动后端服务器**:

```bash
cd edubot-twin-server
../.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

2. **启动前端开发服务器**:

```bash
cd edubot-twin-web
pnpm run dev
```

3. **测试登录**:

- 访问 http://localhost:5173
- 使用测试账号登录:
  - 用户名: `student001`
  - 密码: `123456`

### TODO: 前后端联调任务

- [x] 验证登录流程 (输入账号密码 → 请求后端 → 返回角色信息)
- [x] 验证登录失败场景 (错误密码、不存在用户)
- [x] 检查登录后的路由跳转 (`/student/home`)
- [ ] 验证 Token 存储和使用
- [ ] 测试获取用户信息接口联调
- [x] 检查 CORS 跨域配置是否正常

### 已知问题

> [!NOTE]
> **响应格式匹配**
>
> 后端响应格式已调整为 `{code: 0, ...}` 以兼容前端拦截器,解决了前端请求无法正常返回的问题。

## 📝 许可证

MIT License © 2026 Edubot Twin Team
