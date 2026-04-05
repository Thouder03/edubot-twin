<script setup lang="ts">
/**
 * 实验环境管理页 — /teacher/experiments/environments
 *
 * 左侧：环境包列表（单击选中 / 双击进入文件树+基本设置）+ 右键菜单
 * 右侧：Monaco 编辑器（含 startup.sh 及其他文件）
 * 基本设置区：container_target_dir / access_level（可拖拽分隔）
 * 试运行：复用学生仿真页面（Simulation.vue）
 */
import { ContentWrap } from '@/components/ContentWrap'
import MonacoEditor from '@/components/Monaco/MonacoEditor.vue'
import {
  createEnvBundleApi,
  deleteEnvBundleApi,
  getEnvBundleListApi,
  patchEnvBundleApi,
  startDryRunApi,
  getFileBundleListApi
} from '@/api/experiment'
import type { EnvBundleListItem } from '@/api/experiment/types'
import { useFileOperations } from '@/composables/useFileOperations'
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

// ─── 文件操作 composable ──────────────────────────────────────────────────────

const fileApiPrefix = computed(() =>
  selectedEnvBundle.value
    ? `/api/v1/teachers/env-bundles/${selectedEnvBundle.value.env_bundle_id}/files`
    : ''
)

const {
  fileList,
  loading: fileLoading,
  fileContent,
  openedFilePath,
  hasUnsavedChanges,
  listFiles,
  readFile,
  saveFile,
  confirmLeave
} = useFileOperations(fileApiPrefix, { protectedPaths: ['startup.sh'] })

// ─── 单击选中 ─────────────────────────────────────────────────────────────────

const handleEnvBundleClick = (bundle: EnvBundleListItem) => {
  selectedEnvBundle.value = bundle
}

// ─── 双击进入文件树 ───────────────────────────────────────────────────────────

const handleEnvBundleDblClick = async (bundle: EnvBundleListItem) => {
  selectedEnvBundle.value = bundle
  viewMode.value = 'tree'
  await listFiles()
  // 自动打开 startup.sh
  const startupFile = fileList.value.find((f) => f.name === 'startup.sh')
  if (startupFile) {
    await readFile('startup.sh')
  }
}

// ─── 返回列表 ─────────────────────────────────────────────────────────────────

const handleBackToList = async () => {
  const ok = await confirmLeave()
  if (!ok) return
  viewMode.value = 'list'
  openedFilePath.value = undefined
  fileContent.value = ''
}

// ─── 文件树 ──────────────────────────────────────────────────────────────────

const getFileLanguage = (path: string) => {
  const ext = path.split('.').pop() ?? ''
  const map: Record<string, string> = {
    py: 'python',
    launch: 'xml',
    yaml: 'yaml',
    yml: 'yaml',
    sh: 'shell',
    json: 'json',
    cpp: 'cpp',
    c: 'c',
    txt: 'plaintext',
    md: 'markdown'
  }
  return map[ext] ?? 'plaintext'
}

const getFileIcon = (name: string, type: 'file' | 'dir') => {
  if (type === 'dir') return '📁'
  if (name === 'startup.sh') return '🚀'
  const ext = name.split('.').pop() ?? ''
  const map: Record<string, string> = {
    py: '🐍',
    launch: '⚡',
    yaml: '📋',
    yml: '📋',
    sh: '⚙️',
    md: '📝',
    txt: '📄',
    json: '{}',
    cpp: '💻',
    zip: '🗜️'
  }
  return map[ext] ?? '📄'
}

const handleFileItemClick = async (name: string, type: 'file' | 'dir') => {
  if (type === 'dir') return
  const ok = await confirmLeave()
  if (!ok) return
  await readFile(name)
}

const handleDeleteFile = async (name: string) => {
  if (name === 'startup.sh') {
    ElMessage.warning('启动脚本不可删除')
    return
  }
  await ElMessageBox.confirm(`确认删除 "${name}" 吗？`, '删除确认', {
    confirmButtonText: '确认删除',
    cancelButtonText: '取消',
    type: 'warning'
  })
  try {
    await fetch(`${fileApiPrefix.value}/delete?path=${encodeURIComponent(name)}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${localStorage.getItem('token') ?? ''}` }
    })
    ElMessage.success('已删除')
    if (openedFilePath.value === name) {
      openedFilePath.value = undefined
      fileContent.value = ''
    }
    await listFiles()
  } catch {
    ElMessage.error('删除失败')
  }
}

// ─── 编辑器 ──────────────────────────────────────────────────────────────────

const editorContent = computed({
  get: () => fileContent.value,
  set: (val) => {
    fileContent.value = val
    hasUnsavedChanges.value = true
  }
})

const handleSave = async () => {
  if (!openedFilePath.value) return
  await saveFile(openedFilePath.value, fileContent.value)
}

// ─── 基本设置 ─────────────────────────────────────────────────────────────────

const settingsForm = ref({
  container_target_dir: '/home/ubuntu20/catkin_ws',
  access_level: 'readonly' as 'readonly' | 'readwrite' | 'hidden'
})

// 进入文件树时同步设置
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
  if (hasUnsavedChanges.value) {
    const ok = await confirmLeave()
    if (!ok) return
  }
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

// ─── 左侧面板可拖拽分隔（文件树 / 基本设置） ─────────────────────────────────

const treeHeightPercent = ref(60) // 百分比
const isDragging = ref(false)
const leftPanelRef = ref<HTMLElement | null>(null)

const startDrag = (e: MouseEvent) => {
  isDragging.value = true
  const startY = e.clientY
  const startPercent = treeHeightPercent.value

  const onMove = (ev: MouseEvent) => {
    if (!leftPanelRef.value) return
    const totalH = leftPanelRef.value.clientHeight
    const delta = ((ev.clientY - startY) / totalH) * 100
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

// ─── 上传文件 ─────────────────────────────────────────────────────────────────

const uploadInputRef = ref<HTMLInputElement | null>(null)

const triggerUpload = () => uploadInputRef.value?.click()

const handleUploadChange = async (e: Event) => {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file || !selectedEnvBundle.value) return
  const formData = new FormData()
  formData.append('file', file)
  try {
    const res = await fetch(
      `/api/v1/teachers/env-bundles/${selectedEnvBundle.value.env_bundle_id}/files/upload`,
      {
        method: 'POST',
        body: formData,
        headers: { Authorization: `Bearer ${localStorage.getItem('token') ?? ''}` }
      }
    )
    if (res.ok) {
      ElMessage.success(`"${file.name}" 上传成功`)
      await listFiles()
    } else {
      ElMessage.error('上传失败')
    }
  } catch {
    ElMessage.error('上传失败')
  } finally {
    target.value = ''
  }
}

// ─── 右键菜单 ─────────────────────────────────────────────────────────────────

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

// ─── 重命名 ──────────────────────────────────────────────────────────────────

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

// ─── 删除环境包 ──────────────────────────────────────────────────────────────

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
    if (detail === 'BUNDLE_IN_USE') {
      ElMessage.error('该环境包被版本引用，请先解除关联')
    } else {
      ElMessage.error('删除失败：' + (detail || ''))
    }
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

const dryRunDialogVisible = ref(false)
const dryRunVersionId = ref<string>('')
const dryRunVersions = ref<{ version_id: number; label: string }[]>([])
const dryRunLoading = ref(false)

const openDryRunDialog = async () => {
  if (hasUnsavedChanges.value) {
    const ok = await confirmLeave()
    if (!ok) return
  }
  // 加载可用版本列表
  try {
    await getFileBundleListApi({ page: 1, page_size: 200 })
    // 实际上试运行需要 experiment versions，这里用 file bundle 作临时 placeholder
    // TODO: 从 experiments API 获取版本列表
    dryRunVersions.value = []
  } catch (_e) {
    // 加载版本列表失败时静默忽略，用户仍可手动输入版本ID
  }
  dryRunVersionId.value = ''
  dryRunDialogVisible.value = true
}

const startDryRun = async () => {
  if (!selectedEnvBundle.value) return
  const vid = Number(dryRunVersionId.value)
  if (!vid) {
    ElMessage.warning('请选择关联的实验版本')
    return
  }

  dryRunLoading.value = true
  try {
    const res = await startDryRunApi(selectedEnvBundle.value.env_bundle_id, vid)
    dryRunDialogVisible.value = false
    const { simulation_url, container_id } = res.data
    ElMessage.success('测试容器已就绪，正在跳转仿真工作台...')
    // 跳转学生仿真页（传 dry_run 标记和 container_id）
    const url = router.resolve({
      name: 'Simulation',
      query: {
        dry_run: '1',
        container_id,
        simulation_url,
        env_bundle_name: selectedEnvBundle.value.name
      }
    }).href
    window.open(url, '_blank')
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    if (detail === 'DRY_RUN_RESOURCE_EXHAUSTED') {
      ElMessage.error('测试容器配额已满（最多 3 个），请先关闭已有的测试容器')
    } else {
      ElMessage.error('启动失败：' + (detail || '未知错误'))
    }
  } finally {
    dryRunLoading.value = false
  }
}

// ─── 路由离开前确认 ───────────────────────────────────────────────────────────

onBeforeRouteLeave(async (_to, _from, next) => {
  const ok = await confirmLeave()
  next(ok ? undefined : false)
})
</script>

<template>
  <ContentWrap>
    <!-- 标题栏 -->
    <div class="mb-16px flex items-center justify-between">
      <div class="text-18px font-600">实验环境管理</div>
      <ElButton v-if="viewMode === 'list'" type="primary" @click="openCreateDialog">
        + 新建环境包
      </ElButton>
    </div>

    <div class="exp-envs-layout">
      <!-- ─── 左侧面板 ─── -->
      <div ref="leftPanelRef" class="exp-envs-left">
        <!-- 状态 A：环境包列表 -->
        <template v-if="viewMode === 'list'">
          <ElSkeleton v-if="envBundlesLoading" :rows="4" animated />
          <template v-else>
            <div v-if="envBundles.length === 0" class="empty-hint">
              <ElEmpty>
                <template #description>
                  <div class="text-14px color-#606266">
                    暂无环境包。<br />
                    点击「新建环境包」创建，<br />
                    然后<strong>双击</strong>进入文件树编辑 startup.sh。
                  </div>
                </template>
              </ElEmpty>
            </div>
            <div v-else class="bundle-hint text-12px color-#909399 mb-8px">
              💡 单击选中，<strong>双击</strong>进入文件树
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
            <ElScrollbar class="file-tree-scroll">
              <div v-if="fileLoading" class="pa-12px">
                <ElSkeleton :rows="3" animated />
              </div>
              <div v-else>
                <div
                  v-for="item in fileList"
                  :key="item.name"
                  :class="[
                    'file-tree-item',
                    openedFilePath === item.name && 'file-tree-item--active',
                    item.name === 'startup.sh' && 'file-tree-item--startup'
                  ]"
                  @click="handleFileItemClick(item.name, item.type)"
                >
                  <span class="file-tree-item__icon">{{ getFileIcon(item.name, item.type) }}</span>
                  <span class="file-tree-item__name">{{ item.name }}</span>
                  <ElTag
                    v-if="item.name === 'startup.sh'"
                    type="warning"
                    size="small"
                    class="mr-4px"
                  >
                    受保护
                  </ElTag>
                  <ElButton
                    v-if="item.type === 'file' && item.name !== 'startup.sh'"
                    link
                    type="danger"
                    size="small"
                    class="file-tree-item__del"
                    @click.stop="handleDeleteFile(item.name)"
                  >
                    删除
                  </ElButton>
                </div>
              </div>
            </ElScrollbar>
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
          <div class="settings-area" :style="{ flex: 1 }">
            <div class="settings-header">基本设置</div>
            <ElForm :model="settingsForm" label-position="top" class="settings-form pa-12px">
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

      <!-- ─── 右侧面板 ─── -->
      <div class="exp-envs-right">
        <!-- 列表视图：摘要信息 -->
        <div v-if="viewMode === 'list'" class="right-placeholder">
          <div v-if="!selectedEnvBundle" class="color-#bbb text-14px"> 请先选择一个环境包 </div>
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

        <!-- 文件树视图：MonacoEditor + 操作按钮 -->
        <div v-else class="editor-area">
          <div v-if="!openedFilePath" class="editor-placeholder">
            点击左侧文件树中的文件以打开编辑（含 startup.sh）
          </div>
          <template v-else>
            <div class="editor-toolbar">
              <span class="editor-toolbar__path">
                <span v-if="openedFilePath === 'startup.sh'">🚀</span>
                📄 {{ openedFilePath }}
              </span>
              <ElTag v-if="hasUnsavedChanges" type="warning" size="small">未保存</ElTag>
              <ElButton type="primary" size="small" @click="handleSave">保存</ElButton>
              <ElButton type="warning" size="small" @click="openDryRunDialog">🧪 试运行</ElButton>
            </div>
            <div class="editor-body">
              <MonacoEditor v-model="editorContent" :language="getFileLanguage(openedFilePath)" />
            </div>
          </template>
        </div>
      </div>
    </div>

    <!-- 状态栏 -->
    <div class="exp-envs-statusbar">
      <template v-if="viewMode === 'list'"> 共 {{ envBundles.length }} 个环境包 </template>
      <template v-else>
        {{ selectedEnvBundle?.name }} | 文件数：{{ fileList.length }} | 访问权限：{{
          settingsForm.access_level
        }}
      </template>
    </div>
  </ContentWrap>

  <!-- 右键菜单 -->
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

  <!-- 新建环境包对话框 -->
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

  <!-- 重命名对话框 -->
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

  <!-- 试运行对话框 -->
  <ElDialog v-model="dryRunDialogVisible" title="🧪 试运行" width="480px">
    <div class="mb-12px text-13px color-#606266">
      将为您创建一个临时测试容器，验证当前环境包的启动脚本和 launch 文件是否能正常运行。
      <strong>容器停止后将立即自动清理。</strong>
    </div>
    <ElForm label-width="120px">
      <ElFormItem label="关联实验版本" required>
        <ElInput
          v-model="dryRunVersionId"
          placeholder="输入版本 ID（提供镜像和 launch 配置）"
          type="number"
        />
      </ElFormItem>
    </ElForm>
    <template #footer>
      <ElButton @click="dryRunDialogVisible = false">取消</ElButton>
      <ElButton type="warning" :loading="dryRunLoading" @click="startDryRun"> 启动试运行 </ElButton>
    </template>
  </ElDialog>
</template>

<style lang="less" scoped>
.exp-envs-layout {
  display: grid;
  grid-template-columns: 280px 1fr;
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

.file-tree-area {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 20%;
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

.file-tree-scroll {
  flex: 1;
  overflow: auto;
}

.file-tree-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  cursor: pointer;
  font-size: 13px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  transition: background 0.15s;

  &:hover {
    background: var(--el-fill-color-light);

    .file-tree-item__del {
      opacity: 1;
    }
  }

  &--active {
    background: var(--el-color-primary-light-9);
  }

  &--startup {
    font-weight: 600;
    color: var(--el-color-warning-dark-2);
    background: var(--el-color-warning-light-9);
  }

  &__icon {
    font-size: 15px;
    flex-shrink: 0;
  }

  &__name {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__del {
    opacity: 0;
    transition: opacity 0.15s;
    flex-shrink: 0;
  }
}

.drag-divider {
  height: 8px;
  cursor: row-resize;
  background: var(--el-fill-color);
  border-top: 1px solid var(--el-border-color);
  border-bottom: 1px solid var(--el-border-color);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s;
  flex-shrink: 0;

  &:hover,
  &--active {
    background: var(--el-color-primary-light-8);
  }

  &__hint {
    font-size: 10px;
    color: var(--el-text-color-secondary);
    user-select: none;
  }
}

.settings-area {
  overflow: auto;
  border-top: 1px solid var(--el-border-color-lighter);
}

.settings-header {
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-lighter);
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.settings-form {
  :deep(.el-form-item) {
    margin-bottom: 12px;
  }
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

.editor-area {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.editor-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--el-text-color-secondary);
  font-size: 14px;
}

.editor-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color);
  background: var(--el-fill-color-lighter);
  flex-shrink: 0;

  &__path {
    flex: 1;
    font-size: 13px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--el-text-color-secondary);
  }
}

.editor-body {
  flex: 1;
  overflow: hidden;
}

.exp-envs-statusbar {
  margin-top: 8px;
  padding: 6px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
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
