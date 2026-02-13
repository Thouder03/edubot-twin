# API 架构设计文档

## 架构概览

本项目采用**模块化分层架构**,按角色和功能模块组织 API 端点,实现低耦合、高内聚。

## 目录结构

```
app/api/v1/endpoints/
├── student/                    # 学生模块
│   ├── __init__.py            # 路由聚合器
│   ├── basic.py               # ✅ 基本 CRUD
│   ├── auth.py                # 🔜 待实现: 登录、注册
│   ├── exams.py               # 🔜 待实现: 考试相关
│   ├── containers.py          # 🔜 待实现: 容器操作
│   ├── learning.py            # 🔜 待实现: 学习记录
│   └── homework.py            # 🔜 待实现: 作业提交
├── teacher/                    # 教师模块
│   ├── __init__.py            # ✅ 路由聚合器(占位)
│   ├── basic.py               # 🔜 待实现: 基本 CRUD
│   ├── auth.py                # 🔜 待实现: 登录
│   ├── exams.py               # 🔜 待实现: 考试管理
│   ├── containers.py          # 🔜 待实现: 容器集群管理
│   ├── students.py            # 🔜 待实现: 学生管理
│   └── resources.py           # 🔜 待实现: 资源分发
└── common/                     # 公共模块
    ├── __init__.py            # ✅ 公共功能聚合
    ├── upload.py              # 🔜 待实现: 文件上传
    └── download.py            # 🔜 待实现: 文件下载
```

## 路由层级

### 当前已实现的 API 端点

| 模块          | 端点                           | 功能         | 状态 |
| ------------- | ------------------------------ | ------------ | ---- |
| 学生-基本信息 | GET `/api/v1/students`         | 获取学生列表 | ✅   |
| 学生-基本信息 | GET `/api/v1/students/{id}`    | 获取单个学生 | ✅   |
| 学生-基本信息 | POST `/api/v1/students`        | 创建学生     | ✅   |
| 学生-基本信息 | PUT `/api/v1/students/{id}`    | 更新学生     | ✅   |
| 学生-基本信息 | DELETE `/api/v1/students/{id}` | 删除学生     | ✅   |
| 教师          | GET `/api/v1/teachers`         | 占位符端点   | ✅   |
| 公共          | GET `/api/v1/health`           | 健康检查     | ✅   |

### 未来扩展路径示例

#### 学生模块

- `POST /api/v1/students/auth/login` - 学生登录
- `GET /api/v1/students/exams` - 学生考试列表
- `POST /api/v1/students/containers/start` - 启动容器
- `GET /api/v1/students/learning/stats` - 学习统计
- `POST /api/v1/students/homework/submit` - 提交作业

#### 教师模块

- `POST /api/v1/teachers/auth/login` - 教师登录
- `POST /api/v1/teachers/exams` - 创建考试
- `GET /api/v1/teachers/containers/cluster` - 容器集群状态
- `GET /api/v1/teachers/students/{id}/progress` - 学生进度
- `POST /api/v1/teachers/resources/distribute` - 分发资源

## 架构优势

### 1. 低耦合

- 每个模块独立维护,互不影响
- 单个文件职责单一,易于理解和修改

### 2. 高内聚

- 相关功能聚合在同一模块
- 按业务域组织,便于团队分工

### 3. 易扩展

- 添加新功能只需创建新文件并在 `__init__.py` 中注册
- 不影响现有代码

### 4. 易维护

- 单个文件代码量可控 (建议每个文件不超过 200 行)
- 清晰的目录结构降低理解成本

### 5. 易测试

- 模块化设计便于编写单元测试
- 可独立测试每个端点

## 添加新功能步骤

### 示例: 添加学生考试功能

**1. 创建新文件** `app/api/v1/endpoints/student/exams.py`:

```python
from fastapi import APIRouter, Depends
from app.crud.student import exam as exam_crud
from app.schemas.exam import ExamResponse

router = APIRouter()

@router.get("/", response_model=list[ExamResponse])
async def get_student_exams(student_id: int, db = Depends(get_db)):
    """获取学生的考试列表"""
    return await exam_crud.get_exams_by_student(db, student_id)
```

**2. 在 `student/__init__.py` 中注册**:

```python
from . import basic, exams  # 添加导入

router.include_router(exams.router, prefix="/exams", tags=["学生-考试"])
```

**3. 完成!** API 自动可用于 `/api/v1/students/exams`

## CRUD & Models 同步重构建议

虽然当前 CRUD 和 Models 层仍为单文件,但建议后续同步拆分:

### CRUD 拆分

```
app/crud/
├── student/
│   ├── basic.py      # 学生基本信息 CRUD
│   ├── exam.py       # 考试记录 CRUD
│   └── learning.py   # 学习记录 CRUD
```

### Models 拆分

```
app/models/
├── user.py           # User 基类
├── student.py        # Student
├── teacher.py        # Teacher
├── exam.py           # Exam
└── container.py      # Container
```

## 架构演进历程

### v1.0 (初始版本)

```
endpoints/
└── student.py  # 所有学生 API 在一个文件
```

❌ 问题: 随着功能增多,单文件变得臃肿

### v2.0 (当前版本) ⭐

```
endpoints/
├── student/      # 学生模块目录
│   ├── __init__.py
│   └── basic.py
├── teacher/
│   └── __init__.py
└── common/
    └── __init__.py
```

✅ 优势: 模块化,易扩展,低耦合

### v3.0 (未来规划)

- 引入 Service 层 (在 CRUD 和 API 之间)
- 使用依赖注入容器
- 考虑 DDD (领域驱动设计)

## 开发规范

### 文件命名

- 使用小写蛇形命名: `exams.py`, `containers.py`
- 文件名应清晰表达功能: `auth.py` 而不是 `a.py`

### 代码规范

- 每个端点文件不超过 **200 行**
- 每个端点函数包含清晰的文档字符串
- 使用 Pydantic Schema 进行数据验证

### 路由规范

- 使用语义化的 URL 路径
- RESTful 风格: GET/POST/PUT/DELETE
- 统一的错误处理和响应格式

## 重构验证

### 验证测试结果

| 测试项           | 端点                     | 结果    |
| ---------------- | ------------------------ | ------- |
| 学生列表         | GET `/api/v1/students`   | ✅ 通过 |
| 单个学生         | GET `/api/v1/students/1` | ✅ 通过 |
| 健康检查         | GET `/api/v1/health`     | ✅ 通过 |
| 教师占位         | GET `/api/v1/teachers`   | ✅ 通过 |
| 服务器自动reload | -                        | ✅ 通过 |

**结论**: 架构重构成功,所有现有功能正常运行,无破坏性更改。
