<script setup lang="tsx">
import { ContentWrap } from '@/components/ContentWrap'
import { Dialog } from '@/components/Dialog'
import { Table } from '@/components/Table'
import { useTable } from '@/hooks/web/useTable'
import { CrudSchema, useCrudSchemas } from '@/hooks/web/useCrudSchemas'
import {
  createExperimentApi,
  createExperimentVersionApi,
  getExperimentDetailApi,
  getExperimentListApi,
  publishExperimentVersionApi
} from '@/api/experiment'
import type {
  ExperimentDetailResponse,
  ExperimentListItem,
  ExperimentVersionCreateRequest
} from '@/api/experiment/types'
import {
  ElButton,
  ElDrawer,
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
import { computed, reactive, ref, unref } from 'vue'

const searchForm = reactive({
  keyword: '',
  status: ''
})

const { tableRegister, tableState, tableMethods } = useTable({
  fetchDataApi: async () => {
    const { pageSize, currentPage } = tableState
    const res = await getExperimentListApi({
      page: unref(currentPage),
      page_size: unref(pageSize),
      keyword: searchForm.keyword || undefined,
      status: searchForm.status || undefined
    })

    return {
      list: res.data?.list || [],
      total: res.data?.total || 0
    }
  }
})

const { dataList, loading, currentPage, pageSize, total } = tableState
const { getList } = tableMethods

const statusTagTypeMap: Record<string, '' | 'success' | 'warning' | 'info' | 'danger'> = {
  draft: 'warning',
  active: 'success',
  archived: 'info'
}

const versionStatusTagTypeMap: Record<string, '' | 'success' | 'warning' | 'info' | 'danger'> = {
  draft: 'warning',
  published: 'success',
  deprecated: 'info'
}

const statusLabelMap: Record<string, string> = {
  draft: '草稿',
  active: '启用',
  archived: '归档'
}

const versionStatusLabelMap: Record<string, string> = {
  draft: '草稿',
  published: '已发布',
  deprecated: '已废弃'
}

const crudSchemas = reactive<CrudSchema[]>([
  {
    field: 'experiment_id',
    label: 'ID',
    table: { width: 90 }
  },
  {
    field: 'name',
    label: '实验名称'
  },
  {
    field: 'code',
    label: '实验编码'
  },
  {
    field: 'status',
    label: '状态',
    table: {
      width: 110,
      slots: {
        default: (data: { row: ExperimentListItem }) => (
          <ElTag type={statusTagTypeMap[data.row.status] || 'info'}>
            {statusLabelMap[data.row.status] || data.row.status}
          </ElTag>
        )
      }
    }
  },
  {
    field: 'latest_version',
    label: '最新版本',
    table: {
      slots: {
        default: (data: { row: ExperimentListItem }) => data.row.latest_version || '-'
      }
    }
  },
  {
    field: 'published_at',
    label: '发布时间',
    table: {
      width: 180,
      slots: {
        default: (data: { row: ExperimentListItem }) => data.row.published_at || '-'
      }
    }
  },
  {
    field: 'action',
    label: '操作',
    table: {
      width: 140,
      slots: {
        default: (data: { row: ExperimentListItem }) => (
          <ElButton link type="primary" onClick={() => openDetail(data.row.experiment_id)}>
            版本管理
          </ElButton>
        )
      }
    }
  }
])

const { allSchemas } = useCrudSchemas(crudSchemas)

const createDialogVisible = ref(false)
const createForm = reactive({
  name: '',
  code: '',
  description: ''
})

const detailVisible = ref(false)
const currentExperimentId = ref<number | null>(null)
const detailLoading = ref(false)
const detailData = ref<ExperimentDetailResponse | null>(null)

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

const currentVersions = computed(() => detailData.value?.versions || [])
const currentPublishLogs = computed(() => detailData.value?.publish_logs || [])

const handleSearch = () => {
  currentPage.value = 1
  getList()
}

const handleReset = () => {
  searchForm.keyword = ''
  searchForm.status = ''
  currentPage.value = 1
  getList()
}

const resetCreateForm = () => {
  createForm.name = ''
  createForm.code = ''
  createForm.description = ''
}

const openCreateDialog = () => {
  resetCreateForm()
  createDialogVisible.value = true
}

const submitCreateExperiment = async () => {
  if (!createForm.name.trim() || !createForm.code.trim()) {
    ElMessage.warning('请填写实验名称和实验编码')
    return
  }

  await createExperimentApi({
    name: createForm.name.trim(),
    code: createForm.code.trim(),
    description: createForm.description.trim() || undefined
  })

  ElMessage.success('实验创建成功')
  createDialogVisible.value = false
  getList()
}

const fetchExperimentDetail = async (experimentId: number) => {
  detailLoading.value = true
  try {
    const res = await getExperimentDetailApi(experimentId)
    detailData.value = res.data || null
  } finally {
    detailLoading.value = false
  }
}

const openDetail = async (experimentId: number) => {
  currentExperimentId.value = experimentId
  detailVisible.value = true
  await fetchExperimentDetail(experimentId)
}

const openVersionDialog = () => {
  if (!currentExperimentId.value) {
    ElMessage.warning('当前实验信息缺失')
    return
  }

  versionForm.version_name = ''
  versionForm.environment_key = ''
  versionForm.image_name = 'gzweb_sim:v1'
  versionForm.launch_file_path = '/launch/main.launch'
  versionForm.launch_args_template_text = '{}'
  versionForm.startup_script_ref = ''
  versionForm.file_bundle_id = ''
  versionForm.is_visible = true
  versionDialogVisible.value = true
}

const buildVersionPayload = (): ExperimentVersionCreateRequest | null => {
  if (!versionForm.version_name.trim() || !versionForm.environment_key.trim()) {
    ElMessage.warning('请填写版本号和环境标识')
    return null
  }

  if (!versionForm.launch_file_path.trim()) {
    ElMessage.warning('请填写启动文件路径')
    return null
  }

  let launchArgsTemplate: Record<string, string> = {}
  try {
    const parsed = JSON.parse(versionForm.launch_args_template_text || '{}')
    if (typeof parsed !== 'object' || Array.isArray(parsed) || parsed === null) {
      ElMessage.warning('启动参数模板必须是 JSON 对象')
      return null
    }
    launchArgsTemplate = parsed as Record<string, string>
  } catch {
    ElMessage.warning('启动参数模板 JSON 格式错误')
    return null
  }

  const payload: ExperimentVersionCreateRequest = {
    version_name: versionForm.version_name.trim(),
    environment_key: versionForm.environment_key.trim(),
    image_name: versionForm.image_name.trim() || 'gzweb_sim:v1',
    launch_file_path: versionForm.launch_file_path.trim(),
    launch_args_template: launchArgsTemplate,
    startup_script_ref: versionForm.startup_script_ref.trim() || undefined,
    file_bundle_id: versionForm.file_bundle_id.trim()
      ? Number(versionForm.file_bundle_id)
      : undefined,
    is_visible: versionForm.is_visible
  }

  return payload
}

const submitCreateVersion = async () => {
  if (!currentExperimentId.value) {
    ElMessage.warning('当前实验信息缺失')
    return
  }

  const payload = buildVersionPayload()
  if (!payload) return

  await createExperimentVersionApi(currentExperimentId.value, payload)
  ElMessage.success('版本创建成功')
  versionDialogVisible.value = false
  await fetchExperimentDetail(currentExperimentId.value)
  getList()
}

const publishVersion = async (versionId: number) => {
  if (!currentExperimentId.value) {
    ElMessage.warning('当前实验信息缺失')
    return
  }

  await ElMessageBox.confirm('确认发布该版本吗？发布后学生端将可见。', '发布确认', {
    confirmButtonText: '确认发布',
    cancelButtonText: '取消',
    type: 'warning'
  })

  await publishExperimentVersionApi(currentExperimentId.value, versionId, {
    publish_note: '教师端手动发布'
  })

  ElMessage.success('发布成功')
  await fetchExperimentDetail(currentExperimentId.value)
  getList()
}
</script>

<template>
  <ContentWrap>
    <ElForm :model="searchForm" inline class="mb-16px">
      <ElFormItem label="关键字">
        <ElInput
          v-model="searchForm.keyword"
          placeholder="实验名称 / 编码"
          clearable
          style="width: 220px"
          @keyup.enter="handleSearch"
        />
      </ElFormItem>
      <ElFormItem label="状态">
        <ElSelect v-model="searchForm.status" clearable placeholder="全部" style="width: 140px">
          <ElOption label="草稿" value="draft" />
          <ElOption label="启用" value="active" />
          <ElOption label="归档" value="archived" />
        </ElSelect>
      </ElFormItem>
      <ElFormItem>
        <ElButton type="primary" @click="handleSearch">查询</ElButton>
        <ElButton @click="handleReset">重置</ElButton>
      </ElFormItem>
    </ElForm>

    <div class="mb-10px">
      <ElButton type="primary" @click="openCreateDialog">新增实验</ElButton>
    </div>

    <Table
      v-model:current-page="currentPage"
      v-model:page-size="pageSize"
      :columns="allSchemas.tableColumns"
      :data="dataList"
      :loading="loading"
      :pagination="{ total: unref(total) }"
      @register="tableRegister"
    />
  </ContentWrap>

  <Dialog v-model="createDialogVisible" title="新增实验" width="520px">
    <ElForm label-width="100px">
      <ElFormItem label="实验名称" required>
        <ElInput v-model="createForm.name" placeholder="例如：机器人导航" />
      </ElFormItem>
      <ElFormItem label="实验编码" required>
        <ElInput v-model="createForm.code" placeholder="例如：nav_basic" />
      </ElFormItem>
      <ElFormItem label="描述">
        <ElInput v-model="createForm.description" type="textarea" :rows="3" />
      </ElFormItem>
      <ElFormItem>
        <ElButton type="primary" @click="submitCreateExperiment">保存</ElButton>
        <ElButton @click="createDialogVisible = false">取消</ElButton>
      </ElFormItem>
    </ElForm>
  </Dialog>

  <ElDrawer v-model="detailVisible" title="实验版本管理" size="70%" :destroy-on-close="false">
    <div v-loading="detailLoading">
      <div class="mb-12px flex items-center justify-between">
        <div>
          <div class="text-16px font-600">{{ detailData?.base_info?.name || '-' }}</div>
          <div class="text-12px color-#909399">编码：{{ detailData?.base_info?.code || '-' }}</div>
        </div>
        <ElButton type="primary" @click="openVersionDialog">新增版本</ElButton>
      </div>

      <ElTable :data="currentVersions" border>
        <ElTableColumn prop="version_name" label="版本" min-width="120" />
        <ElTableColumn prop="environment_key" label="环境标识" min-width="140" />
        <ElTableColumn prop="image_name" label="镜像" min-width="160" />
        <ElTableColumn label="状态" width="120">
          <template #default="scope">
            <ElTag :type="versionStatusTagTypeMap[scope.row.publish_status] || 'info'">
              {{ versionStatusLabelMap[scope.row.publish_status] || scope.row.publish_status }}
            </ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="操作" width="140">
          <template #default="scope">
            <ElButton
              link
              type="primary"
              :disabled="scope.row.publish_status !== 'draft'"
              @click="publishVersion(scope.row.version_id)"
            >
              发布
            </ElButton>
          </template>
        </ElTableColumn>
      </ElTable>

      <div class="mt-20px text-14px font-600">发布记录</div>
      <ElTable :data="currentPublishLogs" border class="mt-8px">
        <ElTableColumn prop="publish_id" label="发布ID" width="100" />
        <ElTableColumn prop="version_id" label="版本ID" width="100" />
        <ElTableColumn prop="operator" label="操作人" width="100" />
        <ElTableColumn prop="note" label="备注" min-width="180" />
        <ElTableColumn prop="created_at" label="时间" min-width="180" />
      </ElTable>
    </div>
  </ElDrawer>

  <Dialog v-model="versionDialogVisible" title="新增版本" width="640px">
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
        <ElSelect v-model="versionForm.is_visible" style="width: 120px">
          <ElOption :value="true" label="可见" />
          <ElOption :value="false" label="隐藏" />
        </ElSelect>
      </ElFormItem>
      <ElFormItem>
        <ElButton type="primary" @click="submitCreateVersion">保存</ElButton>
        <ElButton @click="versionDialogVisible = false">取消</ElButton>
      </ElFormItem>
    </ElForm>
  </Dialog>
</template>
