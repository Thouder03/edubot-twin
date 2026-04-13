<script setup lang="ts">
import { ContentWrap } from '@/components/ContentWrap'
import MonacoEditor from '@/components/Monaco/MonacoEditor.vue'
import {
  createExperimentVersionApi,
  deleteExperimentVersionApi,
  getEnvBundleListApi,
  getExperimentDetailApi,
  getFileBundleListApi,
  publishExperimentVersionApi,
  updateExperimentVersionApi,
  updateExperimentVersionPublishStatusApi,
  validateExperimentVersionApi
} from '@/api/experiment'
import type {
  EnvBundleListItem,
  ExperimentDetailResponse,
  ExperimentVersionCreateRequest,
  ExperimentVersionIssue,
  ExperimentVersionResponse,
  ExperimentVersionUpdateRequest,
  FileBundleListItem
} from '@/api/experiment/types'
import {
  ElAlert,
  ElButton,
  ElCard,
  ElDialog,
  ElForm,
  ElFormItem,
  ElInput,
  ElMessage,
  ElMessageBox,
  ElOption,
  ElSelect,
  ElTable,
  ElTableColumn,
  ElTag
} from 'element-plus'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const experimentId = computed(() => Number(route.params.id))

const detailLoading = ref(false)
const detailData = ref<ExperimentDetailResponse | null>(null)
const selectedVersionId = ref<number | null>(null)

// ─── 编辑表单 ─────────────────────────────────────────────────────────────────

const editForm = reactive({
  version_name: '',
  environment_key: '',
  image_name: '',

  file_bundle_id: '' as string | number,
  env_bundle_id: '' as string | number
})
const editorText = ref<string>('{}')

// ─── 验证结果（保存后自动执行，展示黄色警告条） ──────────────────────────────

const validateIssues = ref<ExperimentVersionIssue[]>([])
const validateValid = ref<boolean | null>(null)

// ─── 各版本操作的 loading 状态 ─────────────────────────────────────────────────

const savingVersion = ref(false)
const deletingVersion = ref(false)
const validatingVersion = ref(false)
const changingStatusVersionId = ref<number | null>(null)

// ─── 新建版本对话框 ───────────────────────────────────────────────────────────

const versionDialogVisible = ref(false)
const versionForm = reactive<{
  version_name: string
  environment_key: string
  image_name: string

  launch_args_template_text: string
  file_bundle_id: string
  env_bundle_id: string | number
}>({
  version_name: '',
  environment_key: '',
  image_name: 'gzweb_sim:v1',

  launch_args_template_text: '{}',
  file_bundle_id: '',
  env_bundle_id: ''
})

// ─── 下拉选项数据 ─────────────────────────────────────────────────────────────

const envBundleOptions = ref<EnvBundleListItem[]>([])
const fileBundleOptions = ref<FileBundleListItem[]>([])

const loadEnvBundles = async () => {
  try {
    const res = await getEnvBundleListApi({ page: 1, page_size: 200 })
    envBundleOptions.value = res.data?.list ?? []
  } catch {
    // 静默忽略，不影响主流程
  }
}

const loadFileBundles = async () => {
  try {
    const res = await getFileBundleListApi({ page: 1, page_size: 200 })
    fileBundleOptions.value = res.data?.list ?? []
  } catch {
    // 静默忽略，不影响主流程
  }
}

const imageOptions = computed(() => {
  const merged = new Set<string>(['gzweb_sim:v1'])
  currentVersions.value.forEach((v) => {
    if (v.image_name?.trim()) {
      merged.add(v.image_name)
    }
  })
  return Array.from(merged).map((value) => ({
    label: value,
    value
  }))
})

onMounted(async () => {
  await Promise.all([loadEnvBundles(), loadFileBundles()])
})

// ─── 状态映射 ─────────────────────────────────────────────────────────────────

const versionStatusLabelMap: Record<string, string> = {
  draft: '草稿',
  published: '已发布',
  deprecated: '已废弃'
}

const versionStatusOptions: Array<{ label: string; value: 'draft' | 'published' | 'deprecated' }> =
  [
    { label: '草稿', value: 'draft' },
    { label: '已发布', value: 'published' },
    { label: '已废弃', value: 'deprecated' }
  ]

// ─── 计算属性 ─────────────────────────────────────────────────────────────────

const currentVersions = computed(() => detailData.value?.versions || [])
const currentPublishLogs = computed(() => detailData.value?.publish_logs || [])

const selectedVersion = computed<ExperimentVersionResponse | null>(() => {
  if (!selectedVersionId.value) return null
  return currentVersions.value.find((v) => v.version_id === selectedVersionId.value) || null
})

const handleCurrentVersionChange = (row: ExperimentVersionResponse | null) => {
  // Element Plus 在表格数据刷新时会触发一次 row=null，忽略该瞬时事件以保留当前选中版本
  if (!row) return
  selectedVersionId.value = row.version_id
}

const isDraftVersion = computed(() => selectedVersion.value?.publish_status === 'draft')

// ─── 同步编辑表单 ─────────────────────────────────────────────────────────────

const syncEditFormFromSelected = (version: ExperimentVersionResponse | null) => {
  validateIssues.value = []
  validateValid.value = null
  if (!version) {
    editForm.version_name = ''
    editForm.environment_key = ''
    editForm.image_name = ''

    editForm.file_bundle_id = ''
    editForm.env_bundle_id = ''
    editorText.value = '{}'
    return
  }
  editForm.version_name = version.version_name
  editForm.environment_key = version.environment_key
  editForm.image_name = version.image_name

  editForm.file_bundle_id = version.file_bundle_id ?? ''
  editForm.env_bundle_id = version.env_bundle_id ?? ''
  editorText.value = JSON.stringify(version.launch_args_template || {}, null, 2)
}

watch(selectedVersion, syncEditFormFromSelected, { immediate: true })

// ─── 加载实验详情 ─────────────────────────────────────────────────────────────

const fetchExperimentDetail = async (preferredVersionId?: number | null) => {
  if (!experimentId.value || Number.isNaN(experimentId.value)) {
    ElMessage.error('实验ID无效')
    router.replace('/teacher/experiments/list')
    return
  }

  const keepVersionId = preferredVersionId ?? selectedVersionId.value
  detailLoading.value = true
  try {
    const res = await getExperimentDetailApi(experimentId.value)
    const nextDetail = res.data || null
    const nextVersions = nextDetail?.versions || []

    detailData.value = nextDetail

    if (keepVersionId && nextVersions.some((v) => v.version_id === keepVersionId)) {
      selectedVersionId.value = keepVersionId
    } else {
      selectedVersionId.value = nextVersions[0]?.version_id ?? null
    }
  } finally {
    detailLoading.value = false
  }
}

// ─── 工具函数 ─────────────────────────────────────────────────────────────────

const parseLaunchArgsTemplate = (text: string): Record<string, string> | null => {
  try {
    const parsed = JSON.parse(text || '{}')
    if (typeof parsed !== 'object' || Array.isArray(parsed) || parsed === null) {
      ElMessage.warning('启动参数模板必须是 JSON 对象')
      return null
    }
    return parsed as Record<string, string>
  } catch {
    ElMessage.warning('启动参数模板 JSON 格式错误')
    return null
  }
}

// ─── 验证配置（始终可用） ─────────────────────────────────────────────────────

const validateVersion = async () => {
  if (!selectedVersion.value) {
    ElMessage.warning('请先选择版本')
    return false
  }
  validatingVersion.value = true
  try {
    const res = await validateExperimentVersionApi(
      experimentId.value,
      selectedVersion.value.version_id
    )
    const { valid, issues } = res.data
    validateValid.value = valid
    validateIssues.value = issues || []
    if (valid) {
      ElMessage.success('配置验证通过 ✓')
    }
    return valid
  } catch (e: any) {
    ElMessage.error('验证失败：' + (e?.response?.data?.detail || '未知错误'))
    return false
  } finally {
    validatingVersion.value = false
  }
}

// ─── 保存配置（保存后自动验证） ───────────────────────────────────────────────

const saveVersion = async () => {
  if (!selectedVersion.value) {
    ElMessage.warning('请先选择版本')
    return
  }
  if (!isDraftVersion.value) {
    ElMessage.warning('已发布/已废弃版本为只读，不可编辑')
    return
  }
  if (!editForm.version_name.trim() || !editForm.environment_key.trim()) {
    ElMessage.warning('请填写版本号和环境标识')
    return
  }

  const launchArgsTemplate = parseLaunchArgsTemplate(editorText.value)
  if (!launchArgsTemplate) return

  const payload: ExperimentVersionUpdateRequest = {
    version_name: editForm.version_name.trim(),
    environment_key: editForm.environment_key.trim(),
    image_name: editForm.image_name.trim() || 'gzweb_sim:v1',

    file_bundle_id: editForm.file_bundle_id ? Number(editForm.file_bundle_id) : undefined,
    env_bundle_id: editForm.env_bundle_id ? Number(editForm.env_bundle_id) : undefined,
    launch_args_template: launchArgsTemplate
  }

  savingVersion.value = true
  try {
    const currentVersionId = selectedVersion.value.version_id
    await updateExperimentVersionApi(experimentId.value, currentVersionId, payload)
    ElMessage.success('配置保存成功')
    await fetchExperimentDetail(currentVersionId)
    // 保存后自动验证（SDD §15.3）
    await validateVersion()
  } finally {
    savingVersion.value = false
  }
}

const handleVersionStatusChange = async (
  row: ExperimentVersionResponse,
  targetStatus: 'draft' | 'published' | 'deprecated'
) => {
  if (row.publish_status === targetStatus) return

  changingStatusVersionId.value = row.version_id
  try {
    if (row.publish_status === 'draft' && targetStatus === 'published') {
      await ElMessageBox.confirm('确认发布该版本吗？发布后学生端将可见。', '发布确认', {
        confirmButtonText: '确认发布',
        cancelButtonText: '取消',
        type: 'warning'
      })
      await publishExperimentVersionApi(experimentId.value, row.version_id, {
        publish_note: '教师端手动发布'
      })
    } else if (row.publish_status === 'published' && targetStatus === 'deprecated') {
      await ElMessageBox.confirm(
        '确认废弃该版本吗？废弃后学生不可见，但可重新发布恢复。',
        '废弃版本',
        {
          confirmButtonText: '确认废弃',
          cancelButtonText: '取消',
          type: 'warning'
        }
      )
      await updateExperimentVersionPublishStatusApi(experimentId.value, row.version_id, {
        publish_status: 'deprecated',
        publish_note: '教师手动废弃'
      })
    } else if (row.publish_status === 'deprecated' && targetStatus === 'published') {
      await ElMessageBox.confirm(
        '重新发布前将自动执行配置校验，存在阻断性问题时将拒绝发布。',
        '重新发布',
        { confirmButtonText: '确认重新发布', cancelButtonText: '取消', type: 'warning' }
      )
      await updateExperimentVersionPublishStatusApi(experimentId.value, row.version_id, {
        publish_status: 'published',
        publish_note: '教师重新发布'
      })
    } else {
      await updateExperimentVersionPublishStatusApi(experimentId.value, row.version_id, {
        publish_status: targetStatus,
        publish_note: `教师在版本列表中切换为${versionStatusLabelMap[targetStatus]}`
      })
    }

    ElMessage.success(`状态已切换为${versionStatusLabelMap[targetStatus]}`)
    await fetchExperimentDetail(row.version_id)
  } catch (e: any) {
    if (e === 'cancel' || e === 'close') {
      return
    }

    const detail = e?.response?.data?.detail
    if (detail === 'VALIDATION_BLOCKING_ISSUE') {
      ElMessage.error('配置存在阻断性问题，无法切换为已发布（已自动执行验证）')
      if (selectedVersion.value?.version_id === row.version_id) {
        await validateVersion()
      }
    } else {
      ElMessage.error('状态切换失败：' + (detail || '未知错误'))
    }
    await fetchExperimentDetail(row.version_id)
  } finally {
    changingStatusVersionId.value = null
  }
}

// ─── 删除版本（仅 draft，SDD §15.3） ─────────────────────────────────────────

const deleteVersion = async () => {
  if (!selectedVersion.value || !isDraftVersion.value) {
    ElMessage.warning('仅草稿版本可删除')
    return
  }
  await ElMessageBox.confirm(
    `确认删除版本「${selectedVersion.value.version_name}」吗？此操作不可撤销。`,
    '删除版本',
    { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' }
  )
  deletingVersion.value = true
  try {
    await deleteExperimentVersionApi(experimentId.value, selectedVersion.value.version_id)
    ElMessage.success('版本已删除')
    selectedVersionId.value = null
    await fetchExperimentDetail()
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    if (detail === 'VERSION_NOT_DRAFT') {
      ElMessage.error('仅草稿版本可删除')
    } else {
      ElMessage.error('删除失败：' + (detail || ''))
    }
  } finally {
    deletingVersion.value = false
  }
}

// ─── 新建版本 ─────────────────────────────────────────────────────────────────

const resetVersionForm = () => {
  versionForm.version_name = ''
  versionForm.environment_key = ''
  versionForm.image_name = 'gzweb_sim:v1'

  versionForm.launch_args_template_text = '{}'
  versionForm.file_bundle_id = ''
  versionForm.env_bundle_id = ''
}

const openCreateVersionDialog = () => {
  resetVersionForm()
  versionDialogVisible.value = true
}

const buildVersionCreatePayload = (): ExperimentVersionCreateRequest | null => {
  if (!versionForm.version_name.trim() || !versionForm.environment_key.trim()) {
    ElMessage.warning('请填写版本号和环境标识')
    return null
  }

  const launchArgsTemplate = parseLaunchArgsTemplate(versionForm.launch_args_template_text)
  if (!launchArgsTemplate) return null
  return {
    version_name: versionForm.version_name.trim(),
    environment_key: versionForm.environment_key.trim(),
    image_name: versionForm.image_name.trim() || 'gzweb_sim:v1',

    launch_args_template: launchArgsTemplate,
    file_bundle_id: versionForm.file_bundle_id ? Number(versionForm.file_bundle_id) : undefined,
    env_bundle_id: versionForm.env_bundle_id ? Number(versionForm.env_bundle_id) : undefined
  }
}

const createVersion = async () => {
  const payload = buildVersionCreatePayload()
  if (!payload) return
  await createExperimentVersionApi(experimentId.value, payload)
  ElMessage.success('版本创建成功')
  versionDialogVisible.value = false
  await fetchExperimentDetail()
}

// ─── 严重性颜色映射 ────────────────────────────────────────────────────────────

const issueSeverityType = (
  severity: string
): 'success' | 'warning' | 'info' | 'danger' | 'primary' => {
  return severity === 'blocking' ? 'danger' : 'warning'
}

fetchExperimentDetail()
</script>

<template>
  <ContentWrap>
    <div class="mb-12px flex items-center justify-between">
      <div>
        <div class="text-16px font-600">{{ detailData?.base_info?.name || '-' }}</div>
        <div class="text-12px color-#909399">
          编码：{{ detailData?.base_info?.code || '-' }}（ID:
          {{ detailData?.base_info?.experiment_id || '-' }}）
        </div>
      </div>
      <div class="flex gap-8px">
        <ElButton @click="router.push('/teacher/experiments/list')">返回列表</ElButton>
        <ElButton type="primary" @click="openCreateVersionDialog">新增版本</ElButton>
      </div>
    </div>

    <!-- 验证结果黄色警告条（SDD §15.3） -->
    <ElAlert
      v-if="validateValid === false && validateIssues.length > 0"
      type="warning"
      class="mb-12px"
      :closable="false"
    >
      <template #default>
        <div class="font-600 mb-6px">配置存在以下问题：</div>
        <div v-for="(issue, i) in validateIssues" :key="i" class="flex items-center gap-6px mb-4px">
          <ElTag :type="issueSeverityType(issue.severity)" size="small">
            {{ issue.severity === 'blocking' ? '阻断' : '警告' }}
          </ElTag>
          <span class="text-13px">
            [{{ issue.field }}] {{ issue.message }}（{{ issue.code }}）
          </span>
        </div>
      </template>
    </ElAlert>

    <div class="grid grid-cols-[360px_1fr] gap-12px" v-loading="detailLoading">
      <!-- 左侧：版本列表 + 操作按钮 -->
      <ElCard shadow="never">
        <template #header>
          <div class="font-600">版本列表</div>
        </template>

        <ElTable
          :data="currentVersions"
          row-key="version_id"
          :current-row-key="selectedVersionId || undefined"
          border
          height="520"
          highlight-current-row
          @current-change="handleCurrentVersionChange"
        >
          <ElTableColumn prop="version_name" label="版本" min-width="120" />
          <ElTableColumn prop="environment_key" label="环境标识" min-width="140" />
          <ElTableColumn label="状态" width="130">
            <template #default="scope">
              <ElSelect
                :model-value="scope.row.publish_status"
                size="small"
                style="width: 110px"
                :disabled="changingStatusVersionId === scope.row.version_id"
                @change="
                  (val) =>
                    handleVersionStatusChange(
                      scope.row,
                      val as 'draft' | 'published' | 'deprecated'
                    )
                "
              >
                <ElOption
                  v-for="item in versionStatusOptions"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </ElSelect>
            </template>
          </ElTableColumn>
        </ElTable>

        <!-- 操作按钮区（SDD §15.3） -->
        <div class="mt-12px flex flex-wrap gap-6px">
          <!-- 保存配置：仅 draft 可用 -->
          <ElButton
            type="primary"
            size="small"
            :disabled="!isDraftVersion"
            :loading="savingVersion"
            @click="saveVersion"
          >
            保存配置
          </ElButton>

          <!-- 验证配置：始终可用 -->
          <ElButton
            type="info"
            size="small"
            :disabled="!selectedVersion"
            :loading="validatingVersion"
            @click="validateVersion"
          >
            验证配置
          </ElButton>

          <!-- 删除版本：仅 draft -->
          <ElButton
            type="danger"
            size="small"
            :disabled="!isDraftVersion"
            :loading="deletingVersion"
            @click="deleteVersion"
          >
            删除版本
          </ElButton>
        </div>
      </ElCard>

      <!-- 右侧：配置编辑区 + 发布记录 -->
      <div class="flex flex-col gap-12px">
        <ElCard shadow="never">
          <template #header>
            <div class="flex items-center justify-between">
              <span class="font-600">配置编辑区</span>
              <ElTag :type="isDraftVersion ? 'warning' : 'info'">
                {{ isDraftVersion ? 'draft 可编辑' : 'published/deprecated 只读' }}
              </ElTag>
            </div>
          </template>

          <ElForm label-width="110px" class="mb-12px">
            <ElFormItem label="版本号">
              <ElInput v-model="editForm.version_name" :disabled="!isDraftVersion" />
            </ElFormItem>
            <ElFormItem label="环境标识">
              <ElInput v-model="editForm.environment_key" :disabled="!isDraftVersion" />
            </ElFormItem>
            <ElFormItem label="镜像">
              <ElSelect
                v-model="editForm.image_name"
                :disabled="!isDraftVersion"
                filterable
                allow-create
                default-first-option
                placeholder="请选择或输入镜像"
                style="width: 100%"
              >
                <ElOption
                  v-for="item in imageOptions"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </ElSelect>
            </ElFormItem>

            <ElFormItem label="文件包">
              <ElSelect
                v-model="editForm.file_bundle_id"
                :disabled="!isDraftVersion"
                clearable
                placeholder="请选择文件包（可选）"
                style="width: 100%"
              >
                <ElOption
                  v-for="bundle in fileBundleOptions"
                  :key="bundle.bundle_id"
                  :label="`${bundle.name}（ID: ${bundle.bundle_id}）`"
                  :value="bundle.bundle_id"
                />
              </ElSelect>
            </ElFormItem>
            <!-- env_bundle_id：下拉选择已创建的环境包（SDD §15.3） -->
            <ElFormItem label="环境包">
              <ElSelect
                v-model="editForm.env_bundle_id"
                :disabled="!isDraftVersion"
                clearable
                placeholder="请选择环境包（可选）"
                style="width: 100%"
              >
                <ElOption
                  v-for="eb in envBundleOptions"
                  :key="eb.env_bundle_id"
                  :label="`${eb.name}（ID: ${eb.env_bundle_id}）`"
                  :value="eb.env_bundle_id"
                />
              </ElSelect>
            </ElFormItem>
          </ElForm>

          <div class="mb-8px flex items-center justify-between">
            <span class="text-12px color-#909399">
              launch_args_template（注入启动脚本参数）编辑区：
            </span>
            <ElButton
              type="primary"
              size="small"
              :disabled="!isDraftVersion"
              :loading="savingVersion"
              @click="saveVersion"
            >
              保存配置
            </ElButton>
          </div>

          <div style="height: 360px">
            <MonacoEditor
              v-model="editorText"
              language="json"
              :readonly="!selectedVersion"
              placeholder="请选择版本后编辑 launch_args_template"
              @save="saveVersion"
            />
          </div>
        </ElCard>

        <ElCard shadow="never">
          <template #header>
            <div class="font-600">发布记录</div>
          </template>
          <ElTable :data="currentPublishLogs" border>
            <ElTableColumn prop="publish_id" label="发布ID" width="100" />
            <ElTableColumn prop="version_id" label="版本ID" width="100" />
            <ElTableColumn prop="operator" label="操作人" width="100" />
            <ElTableColumn prop="note" label="备注" min-width="180" />
            <ElTableColumn prop="created_at" label="时间" min-width="180" />
          </ElTable>
        </ElCard>
      </div>
    </div>

    <!-- 新增版本对话框 -->
    <ElDialog v-model="versionDialogVisible" title="新增版本" width="640px">
      <ElForm label-width="120px">
        <ElFormItem label="版本号" required>
          <ElInput v-model="versionForm.version_name" placeholder="例如：v1.0.0" />
        </ElFormItem>
        <ElFormItem label="环境标识" required>
          <ElInput v-model="versionForm.environment_key" placeholder="例如：ros-noetic-nav" />
        </ElFormItem>
        <ElFormItem label="镜像">
          <ElInput v-model="versionForm.image_name" placeholder="gzweb_sim:v1" />
        </ElFormItem>

        <ElFormItem label="启动参数(JSON)">
          <ElInput
            v-model="versionForm.launch_args_template_text"
            type="textarea"
            :rows="3"
            placeholder='例如：{"use_sim_time":"true"}'
          />
        </ElFormItem>
        <ElFormItem label="文件包 ID">
          <ElInput v-model="versionForm.file_bundle_id" placeholder="可选" />
        </ElFormItem>
        <!-- 新增版本时也用下拉选择环境包 -->
        <ElFormItem label="环境包">
          <ElSelect
            v-model="versionForm.env_bundle_id"
            clearable
            placeholder="请选择环境包（可选）"
            style="width: 100%"
          >
            <ElOption
              v-for="eb in envBundleOptions"
              :key="eb.env_bundle_id"
              :label="`${eb.name}（ID: ${eb.env_bundle_id}）`"
              :value="eb.env_bundle_id"
            />
          </ElSelect>
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="versionDialogVisible = false">取消</ElButton>
        <ElButton type="primary" @click="createVersion">保存</ElButton>
      </template>
    </ElDialog>
  </ContentWrap>
</template>
