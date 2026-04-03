<script setup lang="ts">
import { ContentWrap } from '@/components/ContentWrap'
import MonacoEditor from '@/components/Monaco/MonacoEditor.vue'
import {
  createExperimentVersionApi,
  getExperimentDetailApi,
  publishExperimentVersionApi,
  updateExperimentVersionApi
} from '@/api/experiment'
import type {
  ExperimentDetailResponse,
  ExperimentVersionCreateRequest,
  ExperimentVersionResponse,
  ExperimentVersionUpdateRequest
} from '@/api/experiment/types'
import {
  ElButton,
  ElCard,
  ElCheckbox,
  ElDialog,
  ElForm,
  ElFormItem,
  ElInput,
  ElMessage,
  ElMessageBox,
  ElTable,
  ElTableColumn,
  ElTag
} from 'element-plus'
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const experimentId = computed(() => Number(route.params.id))

const detailLoading = ref(false)
const detailData = ref<ExperimentDetailResponse | null>(null)
const selectedVersionId = ref<number | null>(null)

const editForm = reactive({
  version_name: '',
  environment_key: '',
  image_name: '',
  launch_file_path: '',
  startup_script_ref: '',
  file_bundle_id: '',
  is_visible: true
})
const editorText = ref<string>('{}')

const versionDialogVisible = ref(false)
const versionForm = reactive<{
  version_name: string
  environment_key: string
  image_name: string
  launch_file_path: string
  launch_args_template_text: string
  startup_script_ref: string
  file_bundle_id: string
  is_visible: boolean
}>({
  version_name: '',
  environment_key: '',
  image_name: 'gzweb_sim:v1',
  launch_file_path: '/launch/main.launch',
  launch_args_template_text: '{}',
  startup_script_ref: '',
  file_bundle_id: '',
  is_visible: true
})

const versionStatusTagTypeMap: Record<string, '' | 'success' | 'warning' | 'info' | 'danger'> = {
  draft: 'warning',
  published: 'success',
  deprecated: 'info'
}

const versionStatusLabelMap: Record<string, string> = {
  draft: '草稿',
  published: '已发布',
  deprecated: '已废弃'
}

const currentVersions = computed(() => detailData.value?.versions || [])
const currentPublishLogs = computed(() => detailData.value?.publish_logs || [])

const selectedVersion = computed<ExperimentVersionResponse | null>(() => {
  if (!selectedVersionId.value) return null
  return currentVersions.value.find((v) => v.version_id === selectedVersionId.value) || null
})

const isDraftVersion = computed(() => selectedVersion.value?.publish_status === 'draft')

const syncEditFormFromSelected = (version: ExperimentVersionResponse | null) => {
  if (!version) {
    editForm.version_name = ''
    editForm.environment_key = ''
    editForm.image_name = ''
    editForm.launch_file_path = ''
    editForm.startup_script_ref = ''
    editForm.file_bundle_id = ''
    editForm.is_visible = true
    editorText.value = '{}'
    return
  }

  editForm.version_name = version.version_name
  editForm.environment_key = version.environment_key
  editForm.image_name = version.image_name
  editForm.launch_file_path = version.launch_file_path
  editForm.startup_script_ref = version.startup_script_ref || ''
  editForm.file_bundle_id = version.file_bundle_id ? String(version.file_bundle_id) : ''
  editForm.is_visible = version.is_visible
  editorText.value = JSON.stringify(version.launch_args_template || {}, null, 2)
}

watch(
  selectedVersion,
  (version) => {
    syncEditFormFromSelected(version)
  },
  { immediate: true }
)

const fetchExperimentDetail = async () => {
  if (!experimentId.value || Number.isNaN(experimentId.value)) {
    ElMessage.error('实验ID无效')
    router.replace('/teacher/experiments')
    return
  }

  detailLoading.value = true
  try {
    const res = await getExperimentDetailApi(experimentId.value)
    detailData.value = res.data || null

    if (!selectedVersionId.value || !currentVersions.value.some((v) => v.version_id === selectedVersionId.value)) {
      selectedVersionId.value = currentVersions.value[0]?.version_id ?? null
    }
  } finally {
    detailLoading.value = false
  }
}

const resetVersionForm = () => {
  versionForm.version_name = ''
  versionForm.environment_key = ''
  versionForm.image_name = 'gzweb_sim:v1'
  versionForm.launch_file_path = '/launch/main.launch'
  versionForm.launch_args_template_text = '{}'
  versionForm.startup_script_ref = ''
  versionForm.file_bundle_id = ''
  versionForm.is_visible = true
}

const openCreateVersionDialog = () => {
  resetVersionForm()
  versionDialogVisible.value = true
}

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

const buildVersionCreatePayload = (): ExperimentVersionCreateRequest | null => {
  if (!versionForm.version_name.trim() || !versionForm.environment_key.trim()) {
    ElMessage.warning('请填写版本号和环境标识')
    return null
  }

  if (!versionForm.launch_file_path.trim()) {
    ElMessage.warning('请填写启动文件路径')
    return null
  }

  const launchArgsTemplate = parseLaunchArgsTemplate(versionForm.launch_args_template_text)
  if (!launchArgsTemplate) return null

  return {
    version_name: versionForm.version_name.trim(),
    environment_key: versionForm.environment_key.trim(),
    image_name: versionForm.image_name.trim() || 'gzweb_sim:v1',
    launch_file_path: versionForm.launch_file_path.trim(),
    launch_args_template: launchArgsTemplate,
    startup_script_ref: versionForm.startup_script_ref.trim() || undefined,
    file_bundle_id: versionForm.file_bundle_id.trim() ? Number(versionForm.file_bundle_id) : undefined,
    is_visible: versionForm.is_visible
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

const publishVersion = async () => {
  if (!selectedVersion.value) {
    ElMessage.warning('请先选择版本')
    return
  }

  if (selectedVersion.value.publish_status !== 'draft') {
    ElMessage.warning('仅草稿版本允许发布')
    return
  }

  await ElMessageBox.confirm('确认发布该版本吗？发布后学生端将可见。', '发布确认', {
    confirmButtonText: '确认发布',
    cancelButtonText: '取消',
    type: 'warning'
  })

  await publishExperimentVersionApi(experimentId.value, selectedVersion.value.version_id, {
    publish_note: '教师端手动发布'
  })

  ElMessage.success('发布成功')
  await fetchExperimentDetail()
}

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

  if (!editForm.launch_file_path.trim()) {
    ElMessage.warning('请填写启动文件路径')
    return
  }

  const launchArgsTemplate = parseLaunchArgsTemplate(editorText.value)
  if (!launchArgsTemplate) return

  const payload: ExperimentVersionUpdateRequest = {
    version_name: editForm.version_name.trim(),
    environment_key: editForm.environment_key.trim(),
    image_name: editForm.image_name.trim() || 'gzweb_sim:v1',
    launch_file_path: editForm.launch_file_path.trim(),
    startup_script_ref: editForm.startup_script_ref.trim() || undefined,
    file_bundle_id: editForm.file_bundle_id.trim() ? Number(editForm.file_bundle_id) : undefined,
    is_visible: editForm.is_visible,
    launch_args_template: launchArgsTemplate
  }

  await updateExperimentVersionApi(experimentId.value, selectedVersion.value.version_id, payload)
  ElMessage.success('配置保存成功')
  await fetchExperimentDetail()
}

fetchExperimentDetail()
</script>

<template>
  <ContentWrap>
    <div class="mb-12px flex items-center justify-between">
      <div>
        <div class="text-16px font-600">{{ detailData?.base_info?.name || '-' }}</div>
        <div class="text-12px color-#909399">
          编码：{{ detailData?.base_info?.code || '-' }}（ID: {{ detailData?.base_info?.experiment_id || '-' }}）
        </div>
      </div>
      <div class="flex gap-8px">
        <ElButton @click="router.push('/teacher/experiments')">返回列表</ElButton>
        <ElButton type="primary" @click="openCreateVersionDialog">新增版本</ElButton>
      </div>
    </div>

    <div class="grid grid-cols-[360px_1fr] gap-12px" v-loading="detailLoading">
      <ElCard shadow="never">
        <template #header>
          <div class="font-600">版本列表</div>
        </template>

        <ElTable
          :data="currentVersions"
          border
          height="520"
          highlight-current-row
          @current-change="(row) => (selectedVersionId = row?.version_id || null)"
        >
          <ElTableColumn prop="version_name" label="版本" min-width="120" />
          <ElTableColumn prop="environment_key" label="环境标识" min-width="140" />
          <ElTableColumn label="状态" width="110">
            <template #default="scope">
              <ElTag :type="versionStatusTagTypeMap[scope.row.publish_status] || 'info'" size="small">
                {{ versionStatusLabelMap[scope.row.publish_status] || scope.row.publish_status }}
              </ElTag>
            </template>
          </ElTableColumn>
        </ElTable>

        <div class="mt-12px flex gap-8px">
          <ElButton type="primary" :disabled="!isDraftVersion" @click="saveVersion">保存配置</ElButton>
          <ElButton type="success" :disabled="!isDraftVersion" @click="publishVersion">发布版本</ElButton>
        </div>
      </ElCard>

      <div class="flex flex-col gap-12px">
        <ElCard shadow="never">
          <template #header>
            <div class="flex items-center justify-between">
              <span class="font-600">配置编辑区（Monaco）</span>
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
              <ElInput v-model="editForm.image_name" :disabled="!isDraftVersion" />
            </ElFormItem>
            <ElFormItem label="启动文件">
              <ElInput v-model="editForm.launch_file_path" :disabled="!isDraftVersion" />
            </ElFormItem>
            <ElFormItem label="启动脚本引用">
              <ElInput v-model="editForm.startup_script_ref" :disabled="!isDraftVersion" />
            </ElFormItem>
            <ElFormItem label="文件包 ID">
              <ElInput v-model="editForm.file_bundle_id" :disabled="!isDraftVersion" />
            </ElFormItem>
            <ElFormItem label="学生可见">
              <ElCheckbox v-model="editForm.is_visible" :disabled="!isDraftVersion">可见</ElCheckbox>
            </ElFormItem>
          </ElForm>

          <div style="height: 360px">
            <MonacoEditor
              v-model="editorText"
              language="json"
              :readonly="!isDraftVersion"
              placeholder="请选择版本后编辑 launch_args_template"
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
        <ElFormItem label="启动文件" required>
          <ElInput v-model="versionForm.launch_file_path" placeholder="/launch/main.launch" />
        </ElFormItem>
        <ElFormItem label="启动参数(JSON)">
          <ElInput
            v-model="versionForm.launch_args_template_text"
            type="textarea"
            :rows="3"
            placeholder='例如：{"use_sim_time":"true"}'
          />
        </ElFormItem>
        <ElFormItem label="启动脚本引用">
          <ElInput v-model="versionForm.startup_script_ref" placeholder="可选" />
        </ElFormItem>
        <ElFormItem label="文件包 ID">
          <ElInput v-model="versionForm.file_bundle_id" placeholder="可选" />
        </ElFormItem>
        <ElFormItem label="学生可见">
          <ElCheckbox v-model="versionForm.is_visible">可见</ElCheckbox>
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="versionDialogVisible = false">取消</ElButton>
        <ElButton type="primary" @click="createVersion">保存</ElButton>
      </template>
    </ElDialog>
  </ContentWrap>
</template>
