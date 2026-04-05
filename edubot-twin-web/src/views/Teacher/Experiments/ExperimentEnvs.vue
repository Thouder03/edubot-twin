<script setup lang="ts">
/**
 * 实验环境管理页 — /teacher/experiments/environments
 *
 * 左侧：环境包列表 + 文件树（FileTree.vue 完整右键菜单）+ 基本设置（可拖拽调整）
 * 右侧：EditorWorkbench.vue（与学生端相同：标签页 + Ctrl+S + dirty 标记）
 *
 * startup.sh 在文件树中被保护，不可删除，但可在编辑器中正常编辑和保存。
 */
import { ContentWrap } from '@/components/ContentWrap'
import FileTree from '@/views/Simulation/panels/WorkspacePanel/FileTree.vue'
import EditorWorkbench from '@/views/Simulation/panels/WorkspacePanel/EditorWorkbench.vue'
import {
  createEnvBundleApi,
  deleteEnvBundleApi,
  getEnvBundleListApi,
  patchEnvBundleApi,
  startDryRunApi,
  readEnvBundleFileApi,
  saveEnvBundleFileApi
} from '@/api/experiment'
import type { EnvBundleListItem, ExperimentVersionResponse } from '@/api/experiment/types'
import { useBundleWorkspace } from './composables/useBundleWorkspace'
import { useBundleEditorState } from './composables/useBundleEditorState'
import { useWorkspaceSettings } from '@/composables/useWorkspaceSettings'
import {
  ElButton,
  ElDialog,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElInput,
  ElMessage,
  ElMessageBox,
  ElOption,
  ElScrollbar,
  ElSelect,
  ElSkeleton,
  ElTag,
  ElTooltip
} from 'element-plus'
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'

const router = useRouter()

// ─── 视图状态 ─────────────────────────────────────────────────────────────────

type ViewMode = 'list' | 'tree'
const viewMode = ref<ViewMode>('list')

// ─── 环境包列表 ───────────────────────────────────────────────────────────────

const envBundles = ref<EnvBundleListItem[]>([])
const envBundlesLoading = ref(false)
const selectedEnvBundle = ref<EnvBundleListItem | null>(null)

const fetchEnvBundles = async () => {
  envBundlesLoading.value = true
  try {
    const res = await getEnvBundleListApi({ page: 1, page_size: 100 })
    envBundles.value = res.data?.list ?? []
  } finally {
    envBundlesLoading.value = false
  }
}

fetchEnvBundles()

// ─── 环境包 API 前缀 ──────────────────────────────────────────────────────────

const fileApiPrefix = computed(() =>
  selectedEnvBundle.value
    ? `/api/v1/teachers/env-bundles/${selectedEnvBundle.value.env_bundle_id}/files`
    : ''
)

// ─── 文件树（FileTree.vue + startup.sh 保护）─────────────────────────────────

const workspace = useBundleWorkspace(fileApiPrefix, ['startup.sh'])

watch(fileApiPrefix, async (newPrefix) => {
  if (newPrefix && viewMode.value === 'tree') {
    await workspace.loadTree()
  }
})

// ─── 编辑器状态（EditorWorkbench.vue 接口）───────────────────────────────────

const { settings } = useWorkspaceSettings()

const editor = useBundleEditorState(
  async (path: string) => {
    const res = await readEnvBundleFileApi(selectedEnvBundle.value!.env_bundle_id, path)
    return {
      content: res.data?.content ?? '',
      modifiedAt: res.data?.modified_at !== undefined ? Number(res.data.modified_at) : undefined
    }
  },
  async (path: string, content: string, modifiedAt?: number) => {
    const res = await saveEnvBundleFileApi(
      selectedEnvBundle.value!.env_bundle_id,
      path,
      content,
      modifiedAt
    )
    return { newModifiedAt: res.data?.modified_at }
  }
)

// ─── 单击 / 双击环境包 ────────────────────────────────────────────────────────

const handleEnvBundleClick = (bundle: EnvBundleListItem) => {
  selectedEnvBundle.value = bundle
}

const handleEnvBundleDblClick = async (bundle: EnvBundleListItem) => {
  if (editor.hasAnyUnsavedChanges()) {
    const ok = await confirmLeave()
    if (!ok) return
  }
  selectedEnvBundle.value = bundle
  settingsForm.value.container_target_dir =
    (bundle as any).container_target_dir || '/home/ubuntu20/catkin_ws'
  settingsForm.value.access_level = (bundle as any).access_level || 'readonly'
  viewMode.value = 'tree'
  workspace.clearSelection()
  // 关闭旧标签页
  const allPaths = [
    ...editor.pinnedTabs.value,
    ...(editor.previewPath.value ? [editor.previewPath.value] : [])
  ]
  allPaths.forEach((p) => editor.closeTab(p))
  await workspace.loadTree()
  // 自动打开 startup.sh
  const startupNode = workspace.findNodeByPath(workspace.treeData.value, 'startup.sh')
  if (startupNode) {
    await editor.openFile('startup.sh', false) // pinned
  }
}

// ─── 返回列表 ─────────────────────────────────────────────────────────────────

const handleBackToList = async () => {
  const ok = await confirmLeave()
  if (!ok) return
  viewMode.value = 'list'
  const allPaths = [
    ...editor.pinnedTabs.value,
    ...(editor.previewPath.value ? [editor.previewPath.value] : [])
  ]
  allPaths.forEach((p) => editor.closeTab(p))
}

// ─── 点击文件树节点 ───────────────────────────────────────────────────────────

const handleSelectFile = async (path: string) => {
  const node = workspace.findNodeByPath(workspace.treeData.value, path)
  if (!node || node.type === 'directory') return
  await editor.openFile(path, true)
}

// ─── 离开确认 ─────────────────────────────────────────────────────────────────

const confirmLeave = async (): Promise<boolean> => {
  const dirtyPaths = editor.getDirtyPaths()
  if (dirtyPaths.length === 0) return true

  const fileNames = dirtyPaths.map((p) => p.split('/').pop()).join('、')
  try {
    await ElMessageBox.confirm(
      `以下文件有未保存的修改：${fileNames}，是否保存后继续？`,
      '未保存修改',
      {
        confirmButtonText: '全部保存后继续',
        cancelButtonText: '放弃修改并继续',
        distinguishCancelAndClose: true,
        type: 'warning'
      }
    )
    for (const path of dirtyPaths) {
      const cached = editor.fileCache[path]
      const content = cached?.content ?? ''
      await saveEnvBundleFileApi(
        selectedEnvBundle.value!.env_bundle_id,
        path,
        content,
        cached?.modifiedAt
      )
    }
    return true
  } catch (action) {
    if (action === 'cancel') return true
    return false
  }
}

onBeforeRouteLeave(async (_to, _from, next) => {
  const ok = await confirmLeave()
  next(ok ? undefined : false)
})

// ─── 基本设置 ─────────────────────────────────────────────────────────────────

const settingsForm = ref({
  container_target_dir: '/home/ubuntu20/catkin_ws',
  access_level: 'readonly' as 'readonly' | 'readwrite' | 'hidden'
})

watch(selectedEnvBundle, (bundle) => {
  if (bundle) {
    settingsForm.value.container_target_dir =
      (bundle as any).container_target_dir || '/home/ubuntu20/catkin_ws'
    settingsForm.value.access_level = (bundle as any).access_level || 'readonly'
  }
})

const savingSettings = ref(false)
const handleSaveSettings = async () => {
  if (!selectedEnvBundle.value) return
  savingSettings.value = true
  try {
    await patchEnvBundleApi(selectedEnvBundle.value.env_bundle_id, {
      container_target_dir: settingsForm.value.container_target_dir,
      access_level: settingsForm.value.access_level
    })
    ElMessage.success('基本设置已保存')
    await fetchEnvBundles()
  } catch (e: any) {
    ElMessage.error('保存失败：' + (e?.response?.data?.detail || ''))
  } finally {
    savingSettings.value = false
  }
}

// ─── 可拖拽分隔（文件树 / 基本设置）─────────────────────────────────────────

const treeHeightPercent = ref(60)
const isDragging = ref(false)
const leftPanelRef = ref<HTMLElement | null>(null)

const startDrag = (e: MouseEvent) => {
  isDragging.value = true
  const startY = e.clientY
  const startPercent = treeHeightPercent.value
  const onMove = (ev: MouseEvent) => {
    if (!leftPanelRef.value) return
    const delta = ((ev.clientY - startY) / leftPanelRef.value.clientHeight) * 100
    treeHeightPercent.value = Math.max(20, Math.min(80, startPercent + delta))
  }
  const onUp = () => {
    isDragging.value = false
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

// ─── 上传 ─────────────────────────────────────────────────────────────────────

const uploadInputRef = ref<HTMLInputElement | null>(null)
const triggerUpload = () => uploadInputRef.value?.click()
const handleUploadChange = async (e: Event) => {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  await workspace.uploadExternalCommand(file, '.')
  target.value = ''
}

// ─── 环境包列表右键菜单 ──────────────────────────────────────────────────────

const ctxMenu = ref({ visible: false, x: 0, y: 0, bundle: null as EnvBundleListItem | null })
const showCtxMenu = (e: MouseEvent, bundle: EnvBundleListItem) => {
  e.preventDefault()
  ctxMenu.value = { visible: true, x: e.clientX, y: e.clientY, bundle }
}
const hideCtxMenu = () => {
  ctxMenu.value.visible = false
}
onBeforeUnmount(() => document.removeEventListener('click', hideCtxMenu))
nextTick(() => document.addEventListener('click', hideCtxMenu))

// ─── 重命名 / 删除环境包 ─────────────────────────────────────────────────────

const renameDialogVisible = ref(false)
const renameInput = ref('')
const renameBundleId = ref<number | null>(null)

const handleRename = (bundle: EnvBundleListItem) => {
  hideCtxMenu()
  renameBundleId.value = bundle.env_bundle_id
  renameInput.value = bundle.name
  renameDialogVisible.value = true
}

const submitRename = async () => {
  if (!renameBundleId.value || !renameInput.value.trim()) return
  try {
    await patchEnvBundleApi(renameBundleId.value, { name: renameInput.value.trim() })
    ElMessage.success('重命名成功')
    renameDialogVisible.value = false
    await fetchEnvBundles()
  } catch (e: any) {
    ElMessage.error('重命名失败：' + (e?.response?.data?.detail || ''))
  }
}

const handleDeleteBundle = async (bundle: EnvBundleListItem) => {
  hideCtxMenu()
  await ElMessageBox.confirm(`确认删除环境包「${bundle.name}」吗？`, '删除确认', {
    confirmButtonText: '确认删除',
    cancelButtonText: '取消',
    type: 'warning'
  })
  try {
    await deleteEnvBundleApi(bundle.env_bundle_id)
    ElMessage.success('环境包已删除')
    if (selectedEnvBundle.value?.env_bundle_id === bundle.env_bundle_id) {
      selectedEnvBundle.value = null
      viewMode.value = 'list'
    }
    await fetchEnvBundles()
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    ElMessage.error(
      detail === 'BUNDLE_IN_USE'
        ? '该环境包被版本引用，请先解除关联'
        : '删除失败：' + (detail || '')
    )
  }
}

// ─── 新建环境包 ──────────────────────────────────────────────────────────────

const createDialogVisible = ref(false)
const createForm = ref({
  name: '',
  container_target_dir: '/home/ubuntu20/catkin_ws',
  access_level: 'readonly' as 'readonly' | 'readwrite' | 'hidden'
})

const openCreateDialog = () => {
  createForm.value = {
    name: '',
    container_target_dir: '/home/ubuntu20/catkin_ws',
    access_level: 'readonly'
  }
  createDialogVisible.value = true
}

const submitCreateBundle = async () => {
  if (!createForm.value.name.trim()) {
    ElMessage.warning('请输入环境包名称')
    return
  }
  try {
    await createEnvBundleApi({
      name: createForm.value.name.trim(),
      container_target_dir: createForm.value.container_target_dir,
      access_level: createForm.value.access_level
    })
    ElMessage.success('环境包创建成功（已自动生成 startup.sh 模板）')
    createDialogVisible.value = false
    await fetchEnvBundles()
  } catch (e: any) {
    ElMessage.error('创建失败：' + (e?.response?.data?.detail || ''))
  }
}

// ─── Dry Run 试运行 ───────────────────────────────────────────────────────────

// 实验 + 版本两级联动（Dry Run 版本选择）
interface DryRunExperimentItem {
  experiment_id: number
  name: string
}
const dryRunExperiments = ref<DryRunExperimentItem[]>([])
const dryRunVersions = ref<ExperimentVersionResponse[]>([])
const dryRunSelectedExperimentId = ref<number | undefined>(undefined)
const dryRunSelectedVersionId = ref<number | undefined>(undefined)
const dryRunDialogVisible = ref(false)
const dryRunLoading = ref(false)
const dryRunExperimentsLoading = ref(false)

const loadExperimentsForDryRun = async () => {
  dryRunExperimentsLoading.value = true
  try {
    const { getExperimentListApi } = await import('@/api/experiment')
    const res = await getExperimentListApi({ page: 1, page_size: 200 })
    dryRunExperiments.value = (res.data?.list ?? []).map((e) => ({
      experiment_id: e.experiment_id,
      name: e.name
    }))
  } finally {
    dryRunExperimentsLoading.value = false
  }
}

const openDryRunDialog = async () => {
  if (editor.hasAnyUnsavedChanges()) {
    const ok = await confirmLeave()
    if (!ok) return
  }
  dryRunSelectedExperimentId.value = undefined
  dryRunSelectedVersionId.value = undefined
  dryRunVersions.value = []
  dryRunDialogVisible.value = true
  await loadExperimentsForDryRun()
}

const handleDryRunExperimentChange = async (experimentId: number | undefined) => {
  dryRunSelectedVersionId.value = undefined
  dryRunVersions.value = []
  if (!experimentId) return
  try {
    const { getExperimentDetailApi } = await import('@/api/experiment')
    const res = await getExperimentDetailApi(experimentId)
    dryRunVersions.value = res.data?.versions ?? []
  } catch (e: any) {
    ElMessage.error('加载版本列表失败：' + (e?.response?.data?.detail || ''))
  }
}

const startDryRun = async () => {
  if (!selectedEnvBundle.value) return
  if (!dryRunSelectedVersionId.value) {
    ElMessage.warning('请选择关联的实验版本')
    return
  }
  dryRunLoading.value = true
  try {
    const res = await startDryRunApi(
      selectedEnvBundle.value.env_bundle_id,
      dryRunSelectedVersionId.value
    )
    dryRunDialogVisible.value = false
    const { simulation_url, container_id, rosbridge_url } = res.data
    ElMessage.success('测试容器已就绪，正在跳转仿真工作台...')
    const url = router.resolve({
      name: 'Simulation',
      query: {
        dry_run: '1',
        container_id,
        simulation_url,
        rosbridge_url,
        env_bundle_name: selectedEnvBundle.value.name
      }
    }).href
    window.open(url, '_blank')
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    ElMessage.error(
      detail === 'DRY_RUN_RESOURCE_EXHAUSTED'
        ? '测试容器配额已满（最多 3 个），请先关闭已有测试容器'
        : '启动失败：' + (detail || '未知错误')
    )
  } finally {
    dryRunLoading.value = false
  }
}
</script>

<template>
  <ContentWrap>
    <!-- 标题栏 -->
    <div class="mb-16px flex items-center justify-between">
      <div class="text-18px font-600">实验环境管理</div>
      <div class="flex items-center gap-8px">
        <ElButton v-if="viewMode === 'tree'" type="warning" size="small" @click="openDryRunDialog">
          🧪 试运行
        </ElButton>
        <ElButton v-if="viewMode === 'list'" type="primary" @click="openCreateDialog">
          + 新建环境包
        </ElButton>
      </div>
    </div>

    <div class="exp-envs-layout">
      <!-- ─── 左侧面板 ─── -->
      <div ref="leftPanelRef" class="exp-envs-left">
        <!-- 状态 A：环境包列表 -->
        <template v-if="viewMode === 'list'">
          <ElSkeleton v-if="envBundlesLoading" :rows="4" animated class="pa-12px" />
          <template v-else>
            <div v-if="envBundles.length === 0" class="empty-hint">
              <ElEmpty>
                <template #description>
                  <div class="text-14px color-#606266">
                    暂无环境包。<br />点击「新建环境包」创建，<br />
                    然后<strong>双击</strong>进入文件树编辑。
                  </div>
                </template>
              </ElEmpty>
            </div>
            <template v-else>
              <div class="bundle-hint text-12px color-#909399">
                💡 单击选中，<strong>双击</strong>进入文件树 | 右键可重命名/删除
              </div>
              <ElScrollbar class="bundle-list-scroll">
                <div
                  v-for="bundle in envBundles"
                  :key="bundle.env_bundle_id"
                  :class="[
                    'bundle-item',
                    selectedEnvBundle?.env_bundle_id === bundle.env_bundle_id &&
                      'bundle-item--selected'
                  ]"
                  @click="handleEnvBundleClick(bundle)"
                  @dblclick="handleEnvBundleDblClick(bundle)"
                  @contextmenu="showCtxMenu($event, bundle)"
                >
                  <span class="bundle-item__icon">🔧</span>
                  <div class="bundle-item__info">
                    <div class="bundle-item__name">{{ bundle.name }}</div>
                    <div class="bundle-item__meta">{{ bundle.container_target_dir }}</div>
                  </div>
                </div>
              </ElScrollbar>
            </template>
          </template>
        </template>

        <!-- 状态 B：文件树 + 基本设置 -->
        <template v-if="viewMode === 'tree'">
          <!-- 文件树区域 -->
          <div class="file-tree-area" :style="{ height: treeHeightPercent + '%' }">
            <div class="tree-header">
              <ElButton link @click="handleBackToList">← 返回列表</ElButton>
              <div class="tree-header__name">{{ selectedEnvBundle?.name }}</div>
              <ElTooltip content="上传文件">
                <ElButton link type="primary" @click="triggerUpload">↑ 上传</ElButton>
              </ElTooltip>
              <input
                ref="uploadInputRef"
                type="file"
                style="display: none"
                @change="handleUploadChange"
              />
            </div>
            <div class="file-tree-wrap">
              <FileTree
                :tree-data="workspace.treeData.value"
                :loading="workspace.loading.value"
                :workspace="workspace"
                @select-file="handleSelectFile"
                @upload="(file, targetPath) => workspace.uploadExternalCommand(file, targetPath)"
              />
            </div>
          </div>

          <!-- 拖拽分隔条 -->
          <div
            class="drag-divider"
            :class="{ 'drag-divider--active': isDragging }"
            @mousedown="startDrag"
          >
            <span class="drag-divider__hint">↕</span>
          </div>

          <!-- 基本设置区 -->
          <div class="settings-area">
            <div class="settings-header">基本设置</div>
            <ElForm :model="settingsForm" label-position="top" class="pa-12px">
              <ElFormItem label="容器目标目录">
                <ElInput
                  v-model="settingsForm.container_target_dir"
                  placeholder="/home/ubuntu20/catkin_ws"
                />
              </ElFormItem>
              <ElFormItem label="学生访问权限">
                <ElSelect v-model="settingsForm.access_level" style="width: 100%">
                  <ElOption label="只读 (readonly)" value="readonly" />
                  <ElOption label="读写 (readwrite)" value="readwrite" />
                  <ElOption label="隐藏 (hidden)" value="hidden" />
                </ElSelect>
              </ElFormItem>
              <ElFormItem>
                <ElButton
                  type="primary"
                  size="small"
                  :loading="savingSettings"
                  @click="handleSaveSettings"
                >
                  保存设置
                </ElButton>
              </ElFormItem>
            </ElForm>
          </div>
        </template>
      </div>

      <!-- ─── 右侧面板：EditorWorkbench ─── -->
      <div class="exp-envs-right">
        <!-- 列表视图摘要 -->
        <div v-if="viewMode === 'list'" class="right-placeholder">
          <div v-if="!selectedEnvBundle" class="color-#bbb text-14px">请先选择一个环境包</div>
          <div v-else class="bundle-summary">
            <div class="bundle-summary__name">🔧 {{ selectedEnvBundle.name }}</div>
            <div class="mt-8px">
              <ElTag type="info">{{ selectedEnvBundle.container_target_dir }}</ElTag>
            </div>
            <div class="mt-16px color-#909399 text-13px">
              双击环境包名称可进入文件树，编辑 startup.sh 和 launch 文件
            </div>
          </div>
        </div>

        <!-- 文件树视图：EditorWorkbench（标签页 + Ctrl+S） -->
        <EditorWorkbench
          v-else
          :preview-path="editor.previewPath.value"
          :active-path="editor.activePath.value"
          :pinned-tabs="editor.pinnedTabs.value"
          :file-cache="editor.fileCache"
          :dirty-map="editor.dirtyMap"
          :settings="settings"
          @content-change="editor.handleContentChange($event)"
          @save="editor.saveActiveFile($event)"
          @select-tab="editor.handleSelectTab($event, false)"
          @close-tab="editor.closeTab($event)"
        />
      </div>
    </div>

    <!-- 状态栏 -->
    <div class="exp-envs-statusbar">
      <template v-if="viewMode === 'list'">共 {{ envBundles.length }} 个环境包</template>
      <template v-else>
        {{ selectedEnvBundle?.name }} | 访问权限：{{ settingsForm.access_level }}
        <span v-if="editor.getDirtyPaths().length > 0" class="statusbar-dirty">
          ● {{ editor.getDirtyPaths().length }} 个文件未保存
        </span>
      </template>
    </div>
  </ContentWrap>

  <!-- 环境包列表右键菜单 -->
  <div
    v-if="ctxMenu.visible"
    class="ctx-menu"
    :style="{ left: ctxMenu.x + 'px', top: ctxMenu.y + 'px' }"
  >
    <div class="ctx-menu__item" @click="handleRename(ctxMenu.bundle!)">重命名</div>
    <div class="ctx-menu__item ctx-menu__item--danger" @click="handleDeleteBundle(ctxMenu.bundle!)">
      删除
    </div>
  </div>

  <!-- 新建环境包 -->
  <ElDialog v-model="createDialogVisible" title="新建环境包" width="500px">
    <ElForm :model="createForm" label-width="120px">
      <ElFormItem label="环境包名称" required>
        <ElInput v-model="createForm.name" placeholder="例如：导航环境" />
      </ElFormItem>
      <ElFormItem label="容器目标目录">
        <ElInput v-model="createForm.container_target_dir" placeholder="/home/ubuntu20/catkin_ws" />
      </ElFormItem>
      <ElFormItem label="学生访问权限">
        <ElSelect v-model="createForm.access_level" style="width: 100%">
          <ElOption label="只读 (readonly)" value="readonly" />
          <ElOption label="读写 (readwrite)" value="readwrite" />
          <ElOption label="隐藏 (hidden)" value="hidden" />
        </ElSelect>
      </ElFormItem>
    </ElForm>
    <template #footer>
      <ElButton @click="createDialogVisible = false">取消</ElButton>
      <ElButton type="primary" @click="submitCreateBundle">创建</ElButton>
    </template>
  </ElDialog>

  <!-- 重命名环境包 -->
  <ElDialog v-model="renameDialogVisible" title="重命名环境包" width="420px">
    <ElForm label-width="90px">
      <ElFormItem label="新名称" required>
        <ElInput v-model="renameInput" placeholder="输入新名称" @keyup.enter="submitRename" />
      </ElFormItem>
    </ElForm>
    <template #footer>
      <ElButton @click="renameDialogVisible = false">取消</ElButton>
      <ElButton type="primary" @click="submitRename">确认</ElButton>
    </template>
  </ElDialog>

  <!-- Dry Run 对话框 -->
  <ElDialog v-model="dryRunDialogVisible" title="试运行" width="480px">
    <div class="mb-12px text-14px color-#606266">
      创建临时测试容器，验证 startup.sh 和 launch 文件能否正常运行。<br />
      容器结束后立即自动清理。
    </div>
    <ElForm label-width="100px">
      <ElFormItem label="选择实验" required>
        <ElSelect
          v-model="dryRunSelectedExperimentId"
          :loading="dryRunExperimentsLoading"
          placeholder="请选择实验"
          style="width: 100%"
          clearable
          filterable
          @change="handleDryRunExperimentChange"
        >
          <ElOption
            v-for="exp in dryRunExperiments"
            :key="exp.experiment_id"
            :label="exp.name"
            :value="exp.experiment_id"
          />
        </ElSelect>
      </ElFormItem>
      <ElFormItem label="选择版本" required>
        <ElSelect
          v-model="dryRunSelectedVersionId"
          :disabled="!dryRunSelectedExperimentId || dryRunVersions.length === 0"
          placeholder="请选择实验版本"
          style="width: 100%"
          clearable
        >
          <ElOption
            v-for="v in dryRunVersions"
            :key="v.version_id"
            :label="`${v.version_name}（${v.publish_status}）`"
            :value="v.version_id"
          />
        </ElSelect>
      </ElFormItem>
    </ElForm>
    <template #footer>
      <ElButton @click="dryRunDialogVisible = false">取消</ElButton>
      <ElButton type="warning" :loading="dryRunLoading" @click="startDryRun">
        🧪 开始试运行
      </ElButton>
    </template>
  </ElDialog>
</template>

<style lang="less" scoped>
.exp-envs-layout {
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: 12px;
  height: calc(100vh - 260px);
  min-height: 500px;
}

.exp-envs-left {
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color);
}

.exp-envs-right {
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color);
}

.bundle-list-scroll {
  flex: 1;
}

.bundle-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  cursor: pointer;
  border-bottom: 1px solid var(--el-border-color-lighter);
  transition: background 0.2s;
  user-select: none;

  &:hover {
    background: var(--el-fill-color-light);
  }

  &--selected {
    background: var(--el-color-primary-light-9);
    border-left: 3px solid var(--el-color-primary);
  }

  &__icon {
    font-size: 20px;
  }
  &__info {
    flex: 1;
    min-width: 0;
  }

  &__name {
    font-size: 14px;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__meta {
    font-size: 11px;
    color: var(--el-text-color-secondary);
    margin-top: 2px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.bundle-hint {
  padding: 8px 14px 4px;
}

.empty-hint {
  padding: 40px 20px;
  text-align: center;
}

.tree-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color);
  background: var(--el-fill-color-lighter);
  flex-shrink: 0;

  &__name {
    flex: 1;
    font-size: 13px;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.file-tree-area {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex-shrink: 0;
}

.file-tree-wrap {
  flex: 1;
  overflow: hidden;
  position: relative;
}

.drag-divider {
  height: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: row-resize;
  background: var(--el-fill-color);
  border-top: 1px solid var(--el-border-color-light);
  border-bottom: 1px solid var(--el-border-color-light);
  flex-shrink: 0;
  transition: background 0.2s;

  &:hover,
  &--active {
    background: var(--el-color-primary-light-8);
  }
  &__hint {
    font-size: 12px;
    color: var(--el-text-color-secondary);
    line-height: 1;
  }
}

.settings-area {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.settings-header {
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--el-text-color-secondary);
  text-transform: uppercase;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-lighter);
}

.right-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

.bundle-summary {
  text-align: center;

  &__name {
    font-size: 18px;
    font-weight: 600;
    margin-bottom: 12px;
  }
}

.exp-envs-statusbar {
  margin-top: 8px;
  padding: 6px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.statusbar-dirty {
  color: var(--el-color-warning);
  margin-left: 8px;
}

.ctx-menu {
  position: fixed;
  z-index: 9999;
  background: var(--el-bg-color-overlay);
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  min-width: 120px;
  overflow: hidden;

  &__item {
    padding: 9px 18px;
    font-size: 13px;
    cursor: pointer;
    transition: background 0.15s;

    &:hover {
      background: var(--el-fill-color-light);
    }
    &--danger {
      color: var(--el-color-danger);
    }
  }
}
</style>
