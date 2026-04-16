<script setup lang="ts">
import { ContentWrap } from '@/components/ContentWrap'
import { Icon } from '@/components/Icon'
import MonacoEditor from '@/components/Monaco/MonacoEditor.vue'
import { useWorkspaceSettings } from '@/composables/useWorkspaceSettings'
import {
  getExamDetailApi,
  updateExamApi,
  publishExamApi,
  archiveExamApi,
  republishExamApi
} from '@/api/exam'
import { getExamEnvSnapshotListApi } from '@/api/exam/envSnapshots'
import { getExamFileSnapshotListApi } from '@/api/exam/fileSnapshots'
import { getExamEvalScriptListApi } from '@/api/exam/evalScripts'
import AttemptList from './components/AttemptList.vue'
import type {
  ExamResponse,
  ExamEnvSnapshotListItem,
  ExamFileSnapshotListItem,
  ExamEvalScriptListItem
} from '@/api/exam/types'
import {
  ElButton,
  ElCard,
  ElCol,
  ElForm,
  ElFormItem,
  ElInput,
  ElMessage,
  ElMessageBox,
  ElOption,
  ElRow,
  ElSelect,
  ElTag,
  ElTooltip
} from 'element-plus'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

// ─── 各策略字段说明 ────────────────────────────────────────────────────────────

const POLICY_DOCS: Record<string, { label: string; fields: { name: string; desc: string }[] }> = {
  runtime_policy: {
    label: '运行策略',
    fields: [
      { name: 'max_duration_ms', desc: '考试时限（毫秒），默认 600000（10分钟）' },
      { name: 'max_attempts', desc: '学生最多可尝试次数，默认 3' },
      { name: 'allow_debug_before_start', desc: '开始考试前是否允许调试仿真环境，默认 true' },
      { name: 'image', desc: '启动考试容器的镜像' },
      { name: 'launch_args', desc: '考试环境中 roslaunch 的启动参数' }
    ]
  },
  panel_policy: {
    label: '面板策略',
    fields: [
      {
        name: 'lock_panels_during_exam',
        desc: '考试进行中是否锁定面板操作，默认 false（第13期生效）'
      },
      { name: 'allowed_panels', desc: '允许显示的面板列表（第13期生效）' }
    ]
  },
  scoring_policy: {
    label: '评分策略',
    fields: [
      { name: 'pass_threshold', desc: '及格线（0-100），默认 60' },
      {
        name: 'scoring_mode',
        desc: '评分模式：objective_only（纯客观分）或 mixed（第13期人工评分）'
      }
    ]
  },
  sidecar_policy: {
    label: 'Sidecar 策略',
    fields: [
      { name: 'image', desc: 'Sidecar 镜像名，默认 sidecar-runner:v1' },
      { name: 'cpu_limit', desc: 'CPU 核数上限，默认 1.0' },
      { name: 'memory_limit_mb', desc: '内存上限（MB），默认 512' },
      {
        name: 'submission_paths',
        desc: '评测文件路径列表，支持精确路径和通配符（如 ["catkin_ws/src/*", "*.py"]）'
      },
      { name: 'eval_script_id', desc: '关联测评脚本 ID（自动同步）' },
      { name: 'env_snapshot_id', desc: '考试环境快照 ID（自动同步）' },
      { name: 'file_snapshot_id', desc: '考试文件快照 ID（自动同步）' }
    ]
  }
}

const route = useRoute()
const router = useRouter()
const examId = computed(() => Number(route.params.id))
const { settings: monacoSettings } = useWorkspaceSettings()

const exam = ref<ExamResponse | null>(null)
const loading = ref(false)
const saving = ref(false)

// 资源选项
const envSnapshots = ref<ExamEnvSnapshotListItem[]>([])
const fileSnapshots = ref<ExamFileSnapshotListItem[]>([])
const evalScripts = ref<ExamEvalScriptListItem[]>([])

// 编辑表单（独立绑定，debounce 保存）
const editForm = ref({
  name: '',
  description: '',
  exam_mode: '' as string,
  env_snapshot_id: undefined as number | undefined,
  file_snapshot_id: undefined as number | undefined,
  eval_script_id: undefined as number | undefined,
  teacher_comment_template: '',
  runtime_policy: '{}',
  panel_policy: '{}',
  scoring_policy: '{}',
  sidecar_policy: '{}'
})

const statusLabelMap: Record<string, string> = {
  draft: '草稿',
  published: '已发布',
  archived: '已归档'
}

const statusTagTypeMap: Record<string, '' | 'success' | 'warning' | 'info' | 'danger'> = {
  draft: 'warning',
  published: 'success',
  archived: 'info'
}

const modeLabelMap: Record<string, string> = {
  result_run: '结果型自动评测',
  process_run: '过程型操作评测',
  multi_stage_run: '多阶段编排评测'
}

const isPublished = computed(() => exam.value?.status === 'published')
const isDraft = computed(() => exam.value?.status === 'draft')
const isArchived = computed(() => exam.value?.status === 'archived')

// 冻结字段在已发布时 disabled
const frozenDisabled = computed(() => isPublished.value)

async function loadExam() {
  loading.value = true
  try {
    const res = await getExamDetailApi(examId.value)
    exam.value = res.data || null
    if (exam.value) {
      editForm.value.name = exam.value.name
      editForm.value.description = exam.value.description || ''
      editForm.value.exam_mode = exam.value.exam_mode
      editForm.value.env_snapshot_id = exam.value.env_snapshot_id ?? undefined
      editForm.value.file_snapshot_id = exam.value.file_snapshot_id ?? undefined
      editForm.value.eval_script_id = exam.value.eval_script_id ?? undefined
      editForm.value.teacher_comment_template = exam.value.teacher_comment_template || ''
      editForm.value.runtime_policy = JSON.stringify(exam.value.runtime_policy_json || {}, null, 2)
      editForm.value.panel_policy = JSON.stringify(exam.value.panel_policy_json || {}, null, 2)
      editForm.value.scoring_policy = JSON.stringify(exam.value.scoring_policy_json || {}, null, 2)
      editForm.value.sidecar_policy = JSON.stringify(exam.value.sidecar_policy_json || {}, null, 2)
    }
  } catch {
    ElMessage.error('加载考试详情失败')
  } finally {
    loading.value = false
  }
}

async function loadResources() {
  try {
    const [envRes, fileRes, scriptRes] = await Promise.all([
      getExamEnvSnapshotListApi({ page: 1, page_size: 200 }),
      getExamFileSnapshotListApi({ page: 1, page_size: 200 }),
      getExamEvalScriptListApi({ page: 1, page_size: 200 })
    ])
    envSnapshots.value = envRes.data?.items || []
    fileSnapshots.value = fileRes.data?.items || []
    evalScripts.value = scriptRes.data?.items || []
  } catch {
    // 静默处理
  }
}

// JSON 校验辅助
function tryParseJSON(str: string): Record<string, unknown> | null {
  try {
    return JSON.parse(str)
  } catch {
    return null
  }
}

let saveTimer: ReturnType<typeof setTimeout> | null = null

async function saveChanges(manual: boolean = false) {
  if (!exam.value) return
  saving.value = true

  // 构建更新数据
  const updateData: Record<string, unknown> = {}

  if (editForm.value.name !== exam.value.name) updateData.name = editForm.value.name
  if (editForm.value.description !== (exam.value.description || ''))
    updateData.description = editForm.value.description
  if (editForm.value.exam_mode !== exam.value.exam_mode)
    updateData.exam_mode = editForm.value.exam_mode
  if (editForm.value.env_snapshot_id !== exam.value.env_snapshot_id)
    updateData.env_snapshot_id = editForm.value.env_snapshot_id
  if (editForm.value.file_snapshot_id !== exam.value.file_snapshot_id)
    updateData.file_snapshot_id = editForm.value.file_snapshot_id
  if (editForm.value.eval_script_id !== exam.value.eval_script_id)
    updateData.eval_script_id = editForm.value.eval_script_id
  if (editForm.value.teacher_comment_template !== (exam.value.teacher_comment_template || ''))
    updateData.teacher_comment_template = editForm.value.teacher_comment_template

  // JSON 字段
  const rp = tryParseJSON(editForm.value.runtime_policy)
  if (
    rp !== null &&
    editForm.value.runtime_policy !== JSON.stringify(exam.value.runtime_policy_json || {}, null, 2)
  ) {
    updateData.runtime_policy = rp
  }
  const pp = tryParseJSON(editForm.value.panel_policy)
  if (
    pp !== null &&
    editForm.value.panel_policy !== JSON.stringify(exam.value.panel_policy_json || {}, null, 2)
  ) {
    updateData.panel_policy = pp
  }
  const sp = tryParseJSON(editForm.value.scoring_policy)
  if (
    sp !== null &&
    editForm.value.scoring_policy !== JSON.stringify(exam.value.scoring_policy_json || {}, null, 2)
  ) {
    updateData.scoring_policy = sp
  }
  const scp = tryParseJSON(editForm.value.sidecar_policy)
  if (
    scp !== null &&
    editForm.value.sidecar_policy !== JSON.stringify(exam.value.sidecar_policy_json || {}, null, 2)
  ) {
    updateData.sidecar_policy = scp
  }

  // 乐观锁
  updateData.updated_at = exam.value.updated_at

  if (Object.keys(updateData).length <= 1) {
    saving.value = false
    if (manual) ElMessage.success('配置已是最新')
    return
  }

  try {
    const res = await updateExamApi(examId.value, updateData)
    if (res.data) {
      exam.value = res.data
      if (manual) ElMessage.success('保存成功')
    }
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    const detail = err?.response?.data?.detail
    if (detail === 'EXAM_FIELD_FROZEN') {
      ElMessage.error('考试已发布，该字段不可修改')
    } else if (detail === 'EXAM_CONCURRENT_MODIFIED') {
      ElMessage.warning('考试已被其他人修改，请刷新后重试')
      await loadExam()
    } else {
      ElMessage.error('保存失败：' + (detail || '未知错误'))
    }
  } finally {
    saving.value = false
  }
}

function debounceSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(saveChanges, 800)
}

// 监听表单变化自动保存
watch(
  () => [
    editForm.value.name,
    editForm.value.description,
    editForm.value.exam_mode,
    editForm.value.env_snapshot_id,
    editForm.value.file_snapshot_id,
    editForm.value.eval_script_id,
    editForm.value.teacher_comment_template,
    editForm.value.runtime_policy,
    editForm.value.panel_policy,
    editForm.value.scoring_policy,
    editForm.value.sidecar_policy
  ],
  () => {
    if (exam.value && !loading.value) {
      debounceSave()
    }
  }
)

// 发布
async function handlePublish() {
  // 前端校验
  if (!editForm.value.env_snapshot_id) {
    ElMessage.warning('请先关联考试环境')
    return
  }
  if (!editForm.value.file_snapshot_id) {
    ElMessage.warning('请先关联考试文件')
    return
  }
  if (!editForm.value.eval_script_id) {
    ElMessage.warning('请先关联测评脚本')
    return
  }

  await ElMessageBox.confirm('确认发布考试？发布后关键配置字段将被冻结。', '发布确认', {
    confirmButtonText: '确认发布',
    cancelButtonText: '取消',
    type: 'warning'
  })

  try {
    const res = await publishExamApi(examId.value)
    ElMessage.success('考试已发布')
    if (res.data) exam.value = res.data
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    const detail = err?.response?.data?.detail || ''
    if (detail.startsWith('EXAM_PUBLISH_INCOMPLETE')) {
      const missing = detail.split(':')[1] || ''
      ElMessage.error('发布失败，缺失项：' + missing)
    } else {
      ElMessage.error('发布失败：' + detail)
    }
  }
}

async function handleArchive() {
  await ElMessageBox.confirm('确认归档考试？归档后学生端将不可见。', '归档确认', {
    type: 'warning'
  })
  try {
    const res = await archiveExamApi(examId.value)
    ElMessage.success('考试已归档')
    if (res.data) exam.value = res.data
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    ElMessage.error('归档失败：' + (err?.response?.data?.detail || ''))
  }
}

async function handleRepublish() {
  try {
    const res = await republishExamApi(examId.value)
    ElMessage.success('考试已重新发布')
    if (res.data) exam.value = res.data
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    ElMessage.error('重新发布失败：' + (err?.response?.data?.detail || ''))
  }
}

onMounted(() => {
  loadExam()
  loadResources()
})
</script>

<template>
  <ContentWrap v-loading="loading">
    <!-- 顶部操作栏 -->
    <div class="flex items-center justify-between mb-20px">
      <div class="flex items-center gap-12px">
        <ElButton @click="router.push('/teacher/exams/list')"> ← 返回 </ElButton>
        <span class="text-18px font-bold">{{ exam?.name || '考试详情' }}</span>
        <ElTag v-if="exam" :type="statusTagTypeMap[exam.status] || 'info'">
          {{ statusLabelMap[exam.status] || exam.status }}
        </ElTag>
        <span v-if="saving" class="text-12px color-gray">保存中...</span>
      </div>
      <div class="flex gap-8px">
        <ElButton type="primary" @click="() => saveChanges(true)" :loading="saving">
          保存更改
        </ElButton>
        <ElButton v-if="isDraft" type="success" @click="handlePublish"> 发布考试 </ElButton>
        <ElButton v-if="isPublished" type="warning" @click="handleArchive"> 归档 </ElButton>
        <ElButton v-if="isArchived" type="success" @click="handleRepublish"> 重新发布 </ElButton>
      </div>
    </div>

    <ElRow :gutter="20">
      <!-- 左列：基础信息 + 资源引用 -->
      <ElCol :span="10">
        <ElCard shadow="never" class="mb-16px">
          <template #header>
            <span class="font-bold">基础信息</span>
          </template>
          <ElForm label-width="90px" size="default">
            <ElFormItem label="名称">
              <ElInput v-model="editForm.name" />
            </ElFormItem>
            <ElFormItem label="编码">
              <ElInput :model-value="exam?.code" disabled />
            </ElFormItem>
            <ElFormItem>
              <template #label>
                <span class="flex items-center gap-4px">
                  模式
                  <Icon v-if="frozenDisabled" icon="vi-ep:lock" color="#909399" :size="12" />
                </span>
              </template>
              <ElSelect v-model="editForm.exam_mode" :disabled="frozenDisabled" style="width: 100%">
                <ElOption
                  v-for="(label, key) in modeLabelMap"
                  :key="key"
                  :label="label"
                  :value="key"
                />
              </ElSelect>
            </ElFormItem>
            <ElFormItem label="说明">
              <ElInput v-model="editForm.description" type="textarea" :rows="2" />
            </ElFormItem>
          </ElForm>
        </ElCard>

        <ElCard shadow="never" class="mb-16px">
          <template #header>
            <div class="flex items-center gap-8px">
              <span class="font-bold">资源引用</span>
              <ElTag v-if="frozenDisabled" size="small" type="info"> 🔒 已冻结 </ElTag>
            </div>
          </template>
          <ElForm label-width="90px" size="default">
            <ElFormItem>
              <template #label>
                <span class="flex items-center gap-4px">
                  测评脚本
                  <Icon v-if="frozenDisabled" icon="vi-ep:lock" color="#909399" :size="12" />
                </span>
              </template>
              <ElSelect
                v-model="editForm.eval_script_id"
                :disabled="frozenDisabled"
                clearable
                placeholder="选择测评脚本"
                style="width: 100%"
              >
                <ElOption
                  v-for="s in evalScripts"
                  :key="s.id"
                  :label="`${s.name} (${s.validate_status})`"
                  :value="s.id"
                />
              </ElSelect>
            </ElFormItem>
            <ElFormItem>
              <template #label>
                <span class="flex items-center gap-4px">
                  考试环境
                  <Icon v-if="frozenDisabled" icon="vi-ep:lock" color="#909399" :size="12" />
                </span>
              </template>
              <ElSelect
                v-model="editForm.env_snapshot_id"
                :disabled="frozenDisabled"
                clearable
                placeholder="选择考试环境"
                style="width: 100%"
              >
                <ElOption
                  v-for="s in envSnapshots"
                  :key="s.id"
                  :label="`${s.name} (${s.file_count}文件)`"
                  :value="s.id"
                />
              </ElSelect>
            </ElFormItem>
            <ElFormItem>
              <template #label>
                <span class="flex items-center gap-4px">
                  考试文件
                  <Icon v-if="frozenDisabled" icon="vi-ep:lock" color="#909399" :size="12" />
                </span>
              </template>
              <ElSelect
                v-model="editForm.file_snapshot_id"
                :disabled="frozenDisabled"
                clearable
                placeholder="选择考试文件"
                style="width: 100%"
              >
                <ElOption
                  v-for="s in fileSnapshots"
                  :key="s.id"
                  :label="`${s.name} (${s.file_count}文件)`"
                  :value="s.id"
                />
              </ElSelect>
            </ElFormItem>
          </ElForm>
        </ElCard>

        <ElCard shadow="never">
          <template #header>
            <span class="font-bold">教师评语模板</span>
          </template>
          <ElInput
            v-model="editForm.teacher_comment_template"
            type="textarea"
            :rows="4"
            placeholder="教师评语模板（可选）"
          />
        </ElCard>
      </ElCol>

      <!-- 右列：策略 JSON 编辑（Monaco） -->
      <ElCol :span="14">
        <ElCard shadow="never" class="mb-16px">
          <template #header>
            <div class="flex items-center gap-8px">
              <span class="font-bold">运行策略 runtime_policy</span>
              <ElTooltip placement="top" :show-after="200">
                <template #content>
                  <div class="policy-tooltip">
                    <div
                      v-for="f in POLICY_DOCS.runtime_policy.fields"
                      :key="f.name"
                      class="policy-tooltip__row"
                    >
                      <code>{{ f.name }}</code
                      >{{ f.desc }}
                    </div>
                  </div>
                </template>
                <Icon
                  icon="vi-carbon:information"
                  color="#909399"
                  :size="14"
                  style="cursor: help"
                />
              </ElTooltip>
            </div>
          </template>
          <div class="monaco-card monaco-card--short">
            <MonacoEditor
              v-model="editForm.runtime_policy"
              language="json"
              :settings="monacoSettings"
            />
          </div>
        </ElCard>

        <ElCard shadow="never" class="mb-16px">
          <template #header>
            <div class="flex items-center gap-8px">
              <span class="font-bold">面板策略 panel_policy</span>
              <ElTooltip placement="top" :show-after="200">
                <template #content>
                  <div class="policy-tooltip">
                    <div
                      v-for="f in POLICY_DOCS.panel_policy.fields"
                      :key="f.name"
                      class="policy-tooltip__row"
                    >
                      <code>{{ f.name }}</code
                      >{{ f.desc }}
                    </div>
                  </div>
                </template>
                <Icon
                  icon="vi-carbon:information"
                  color="#909399"
                  :size="14"
                  style="cursor: help"
                />
              </ElTooltip>
            </div>
          </template>
          <div class="monaco-card">
            <MonacoEditor
              v-model="editForm.panel_policy"
              language="json"
              :settings="monacoSettings"
            />
          </div>
        </ElCard>

        <ElCard shadow="never" class="mb-16px">
          <template #header>
            <div class="flex items-center gap-8px">
              <span class="font-bold">评分策略 scoring_policy</span>
              <ElTooltip placement="top" :show-after="200">
                <template #content>
                  <div class="policy-tooltip">
                    <div
                      v-for="f in POLICY_DOCS.scoring_policy.fields"
                      :key="f.name"
                      class="policy-tooltip__row"
                    >
                      <code>{{ f.name }}</code
                      >{{ f.desc }}
                    </div>
                  </div>
                </template>
                <Icon
                  icon="vi-carbon:information"
                  color="#909399"
                  :size="14"
                  style="cursor: help"
                />
              </ElTooltip>
            </div>
          </template>
          <div class="monaco-card monaco-card--short">
            <MonacoEditor
              v-model="editForm.scoring_policy"
              language="json"
              :settings="monacoSettings"
            />
          </div>
        </ElCard>

        <ElCard shadow="never">
          <template #header>
            <div class="flex items-center gap-8px">
              <span class="font-bold">Sidecar 策略 sidecar_policy</span>
              <ElTooltip placement="top" :show-after="200">
                <template #content>
                  <div class="policy-tooltip">
                    <div
                      v-for="f in POLICY_DOCS.sidecar_policy.fields"
                      :key="f.name"
                      class="policy-tooltip__row"
                    >
                      <code>{{ f.name }}</code
                      >{{ f.desc }}
                    </div>
                  </div>
                </template>
                <Icon
                  icon="vi-carbon:information"
                  color="#909399"
                  :size="14"
                  style="cursor: help"
                />
              </ElTooltip>
              <Icon v-if="frozenDisabled" icon="vi-ep:lock" color="#909399" :size="14" />
              <ElTag v-if="frozenDisabled" size="small" type="info"> 已冻结 </ElTag>
            </div>
          </template>
          <div class="monaco-card">
            <MonacoEditor
              v-model="editForm.sidecar_policy"
              language="json"
              :readonly="frozenDisabled"
              :settings="monacoSettings"
            />
          </div>
        </ElCard>
      </ElCol>
    </ElRow>

    <!-- 运行记录面板（第12期） -->
    <ElCard v-if="exam" shadow="never" class="mt-20px">
      <template #header>
        <span class="font-bold">运行记录</span>
      </template>
      <AttemptList :exam-id="examId" />
    </ElCard>
  </ContentWrap>
</template>

<style lang="less" scoped>
.monaco-card {
  height: 240px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  overflow: hidden;

  &--short {
    height: 160px;
  }
}
</style>

<style lang="less">
/* tooltip 内容不能 scoped，因为渲染在 teleport 层 */
.policy-tooltip {
  max-width: 360px;

  &__row {
    display: flex;
    align-items: flex-start;
    gap: 6px;
    padding: 3px 0;
    font-size: 12px;
    line-height: 1.5;

    code {
      flex-shrink: 0;
      background: rgba(255, 255, 255, 0.12);
      padding: 0 5px;
      border-radius: 3px;
      font-family: monospace;
      color: #a8d8f0;
    }
  }
}
</style>
