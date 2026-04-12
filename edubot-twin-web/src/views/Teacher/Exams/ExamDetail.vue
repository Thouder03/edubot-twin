<script setup lang="ts">
import { ContentWrap } from '@/components/ContentWrap'
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
  ElTag
} from 'element-plus'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const examId = computed(() => Number(route.params.id))

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

async function saveChanges() {
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
  if (rp !== null) updateData.runtime_policy = rp
  const pp = tryParseJSON(editForm.value.panel_policy)
  if (pp !== null) updateData.panel_policy = pp
  const sp = tryParseJSON(editForm.value.scoring_policy)
  if (sp !== null) updateData.scoring_policy = sp
  const scp = tryParseJSON(editForm.value.sidecar_policy)
  if (scp !== null) updateData.sidecar_policy = scp

  // 乐观锁
  updateData.updated_at = exam.value.updated_at

  if (Object.keys(updateData).length <= 1) {
    saving.value = false
    return
  }

  try {
    const res = await updateExamApi(examId.value, updateData)
    if (res.data) {
      exam.value = res.data
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
            <ElFormItem label="模式">
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
            <ElFormItem label="测评脚本">
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
            <ElFormItem label="考试环境">
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
            <ElFormItem label="考试文件">
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

      <!-- 右列：策略 JSON 编辑 -->
      <ElCol :span="14">
        <ElCard shadow="never" class="mb-16px">
          <template #header>
            <span class="font-bold">运行策略 runtime_policy</span>
          </template>
          <ElInput v-model="editForm.runtime_policy" type="textarea" :rows="8" class="font-mono" />
        </ElCard>

        <ElCard shadow="never" class="mb-16px">
          <template #header>
            <span class="font-bold">面板策略 panel_policy</span>
          </template>
          <ElInput v-model="editForm.panel_policy" type="textarea" :rows="8" class="font-mono" />
        </ElCard>

        <ElCard shadow="never" class="mb-16px">
          <template #header>
            <span class="font-bold">评分策略 scoring_policy</span>
          </template>
          <ElInput v-model="editForm.scoring_policy" type="textarea" :rows="8" class="font-mono" />
        </ElCard>

        <ElCard shadow="never">
          <template #header>
            <div class="flex items-center gap-8px">
              <span class="font-bold">Sidecar 策略 sidecar_policy</span>
              <ElTag v-if="frozenDisabled" size="small" type="info"> 🔒 已冻结 </ElTag>
            </div>
          </template>
          <ElInput
            v-model="editForm.sidecar_policy"
            type="textarea"
            :rows="5"
            :disabled="frozenDisabled"
            class="font-mono"
          />
        </ElCard>
      </ElCol>
    </ElRow>
  </ContentWrap>
</template>
