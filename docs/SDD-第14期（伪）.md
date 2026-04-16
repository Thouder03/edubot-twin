# 考试评测文件范围控制 & 教师查看学生提交代码

## 背景

本次实现两个独立但相关的功能：

1. **评测文件范围控制**：考试设置中可指定"哪些文件/文件夹参与自动评测"，Sidecar 容器启动时只将指定路径（而非整个 workspace）复制到 `/opt/submission` 挂载卷。
2. **教师查看提交代码**：在考试复核页添加"查看提交代码"按钮，进入基于 `BundleWorkspaceTemplate` 的只读代码浏览页面（文件树下载专用，不可保存）。

---

## User Review Required

> [!IMPORTANT]
> **评测文件路径格式**：`sidecar_policy_json.submission_paths` 字段接受路径列表，示例：
> ```json
> {
>   "submission_paths": ["src/", "scripts/navigate.py"]
> }
> ```
> - 留空（`[]` 或 `null`）表示复制**全部文件**（保持现有行为）
> - 支持文件或目录（目录含尾斜杠或不含均可）
> - 路径相对于学生 workspace 根目录

> [!IMPORTANT]
> **后端教师鉴权**：学生提交代码的查看端点使用 `get_current_teacher`（教师 token），不需要携带学生 token，直接通过 `attempt_id` 定位到 `submission_snapshot_path`。

---

## Proposed Changes

### 1. 后端：评测文件范围控制

---

#### [MODIFY] [workspace_snapshot.py](file:///home/ubuntu20/code/edubot-twin/edubot-twin-server/app/core/workspace_snapshot.py)

`create_code_snapshot` 函数新增 `submission_paths: list[str] | None` 参数：
- 若为空或 `None`：`shutil.copytree` 复制整个 workspace（现有行为）
- 若非空：只复制列表中指定的相对路径（文件或目录）
  - 使用 `shutil.copy2` / `shutil.copytree` 按路径精确复制到 `target_content/`
  - 跳过 workspace 中不存在的路径（记录 warning log）

---

#### [MODIFY] [sidecar_manager.py](file:///home/ubuntu20/code/edubot-twin/edubot-twin-server/app/core/sidecar_manager.py)

`schedule_sidecar` 调用 `create_code_snapshot` 时，从 `attempt.attempt_sidecar_policy_json` 中提取 `submission_paths` 字段并传入。

---

### 2. 后端：教师查看学生提交代码端点（端点工厂）

---

#### [MODIFY] [exam_attempts_review.py](file:///home/ubuntu20/code/edubot-twin/edubot-twin-server/app/api/v1/endpoints/teacher/exam_attempts_review.py)

新增端点，使用 `build_bundle_files_router` 工厂（只读模式变通方案）：

```
GET  /teachers/exam-attempts/{attempt_id}/submission/files        → 列目录
GET  /teachers/exam-attempts/{attempt_id}/submission/files/read   → 读文件（用于预览）
GET  /teachers/exam-attempts/{attempt_id}/submission/files/download → 下载文件/目录
```

**实现方案**：不直接使用工厂（工厂 resolver 设计为 bundle 模型），改为手动实现三个只读端点：
- 统一用 `attempt.submission_snapshot_path` 定位快照目录
- 鉴权：`get_current_teacher`（只需登录教师即可，无需校验归属）
- 只实现 `list` / `read` / `download` 三个只读操作，无上传/删除/保存

这三个端点挂载在 teacher router 中，前缀为 `/exam-attempts/{attempt_id}/submission`。

---

#### [MODIFY] [teacher/__init__.py](file:///home/ubuntu20/code/edubot-twin/edubot-twin-server/app/api/v1/endpoints/teacher/__init__.py)

无需修改，因为新端点直接注册到 `exam_attempts_review.router`（已注册）。

---

### 3. 前端：教师查看学生提交代码页

---

#### [NEW] ExamAttemptSubmission.vue

路径：`edubot-twin-web/src/views/Teacher/Exams/ExamAttemptSubmission.vue`

- 使用 `BundleWorkspaceTemplate` 包装，传入：
  - `buildApiPrefix`: 固定返回 `/api/v1/teachers/exam-attempts/${attemptId}/submission`
  - `items`：仅一条数据（当前 attempt），直接进入 tree 模式
  - `protectedPaths`：`[]`（不阻止任何操作，但下方通过 `readonly` 实现只读）
  - 覆盖 `#tree-header` slot：只显示下载按钮，不显示上传
- **只读实现**：
  - `BundleWorkspaceTemplate` 有 `#tree-header` slot，覆盖后隐藏上传按钮
  - 由于后端不提供 `save`/`upload`/`delete` 端点，即使前端发送也会返回 404
  - 编辑器通过 `readonly` prop 传递给 EditorWorkbench

> [!WARNING]
> `BundleWorkspaceTemplate` 本身没有 `readonly` prop，需要评估是否添加该 prop 来使 `EditorWorkbench` 进入只读模式（或接受用户保存按钮点击失败，因为后端无 save 端点）。
>
> **推荐方案**：给 `BundleWorkspaceTemplate` 添加 `readonly?: boolean` prop，当为 `true` 时：隐藏保存按钮、`#tree-header` 只显示下载按钮、editor 以只读模式打开。

---

#### [MODIFY] [BundleWorkspaceTemplate.vue](file:///home/ubuntu20/code/edubot-twin/edubot-twin-web/src/views/Teacher/Exams/components/BundleWorkspaceTemplate.vue)

新增 `readonly?: boolean` prop（默认 false）：
- 隐藏标题栏的「保存 (Ctrl+S)」按钮
- `#tree-header` slot 默认内容改为：
  - `readonly=false`：上传按钮（现有行为）
  - `readonly=true`：不显示上传按钮（或不提供默认值，让父组件 slot 自己控制）
- 传递给 EditorWorkbench 的 `readonly` prop（需检查 EditorWorkbench 是否支持）

---

#### [NEW] 前端 API 函数

在 `edubot-twin-web/src/api/exam/attempts.ts` 中新增：
```typescript
/** 获取学生提交代码文件列表 */
export const getSubmissionFilesApi = (attemptId: number, path?: string)
/** 读取提交代码文件内容 */
export const readSubmissionFileApi = (attemptId: number, path: string)
/** 下载提交代码文件（URL 生成） */
export const getSubmissionDownloadUrl = (attemptId: number, path: string): string
```

---

#### [MODIFY] [router/index.ts](file:///home/ubuntu20/code/edubot-twin/edubot-twin-web/src/router/index.ts)

在 `TeacherExams` children 中添加：
```typescript
{
  path: 'attempts/:attempt_id/submission',
  component: () => import('@/views/Teacher/Exams/ExamAttemptSubmission.vue'),
  name: 'TeacherExamAttemptSubmission',
  meta: {
    title: '查看提交代码',
    noTagsView: true, noCache: true, hidden: true, canTo: true,
    activeMenu: '/teacher/exams/list'
  }
}
```

---

#### [MODIFY] [mock/role/index.mock.ts](file:///home/ubuntu20/code/edubot-twin/edubot-twin-web/mock/role/index.mock.ts)

teacher 角色路由列表添加：
- `/teacher/exams/attempts/:attempt_id/submission`

---

#### [MODIFY] [ExamAttemptReview.vue](file:///home/ubuntu20/code/edubot-twin/edubot-twin-web/src/views/Teacher/Exams/ExamAttemptReview.vue)

在 `review-header` 右侧添加一个按钮：

```html
<el-button 
  v-if="attempt?.submission_snapshot_path"
  type="primary" link 
  @click="router.push(`/teacher/exams/attempts/${attemptId}/submission`)"
>
  📂 查看提交代码
</el-button>
```

需要在 `TeacherAttemptFull` 类型中添加 `submission_snapshot_path: string | null`（目前前端类型定义中缺少此字段）。

---

### 4. 后端 Schema 补充

#### [MODIFY] [schemas/exam_attempt.py](file:///home/ubuntu20/code/edubot-twin/edubot-twin-server/app/schemas/exam_attempt.py)

`TeacherAttemptFullSchema` 中添加 `submission_snapshot_path: Optional[str]` 字段。

---

## Verification Plan

### Backend Tests
- 配置 `submission_paths: ["src/"]` 的 sidecar_policy，触发考试，验证 `/opt/submission` 只包含 `src/` 目录内容
- 调用 `GET /teachers/exam-attempts/{id}/submission/files` 端点，验证返回 attempt 快照的文件树

### Frontend Tests
- 进入考试复核页，验证"查看提交代码"按钮出现（当 attempt 已完成且有 submission_snapshot_path）
- 点击进入代码浏览页，验证文件树正常显示、编辑器只读、文件树下载功能正常
