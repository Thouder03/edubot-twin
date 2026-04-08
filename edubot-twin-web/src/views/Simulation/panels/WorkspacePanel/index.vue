<script setup lang="ts">
/**
 * WorkspacePanel/index.vue — 工作区面板（左右分栏）
 *
 * 左侧: FileTree（文件树）
 * 右侧: MonacoEditor（代码编辑器）
 *
 * 能力模型（三种身份）：
 *   shadow + USR  — 服务器端学生工作区（FILES_API_BASE，相对路径）
 *   shadow + ROOT — 容器全文件系统 Sidecar（SHADOW_CONTAINER_FILES_API_BASE，绝对路径）
 *   student       — 容器 Sidecar，student_limited scope（CONTAINER_FILES_API_BASE，绝对路径）
 *                   通过路径预设按钮切换当前根目录
 */
import { onMounted, ref, computed, onUnmounted, watch } from 'vue'
import { onBeforeRouteLeave, useRoute } from 'vue-router'
import { ElButton, ElTooltip } from 'element-plus'
import FileTree from './FileTree.vue'
import EditorWorkbench from './EditorWorkbench.vue'
import { useWorkspace } from './composables/useWorkspace'
import { useWorkspaceSettings, type WorkspaceSettings } from '@/composables/useWorkspaceSettings'
import { useDesign } from '@/hooks/web/useDesign'
import { Icon } from '@/components/Icon'
import { usePanelState } from '@/views/Simulation/stores/panelState'
import { buildSettingsTree, createActionHandler } from './settings'
import {
  FILES_API_BASE,
  CONTAINER_FILES_API_BASE,
  SHADOW_CONTAINER_FILES_API_BASE
} from '@/api/files'

const { getPrefixCls } = useDesign()
const prefixCls = getPrefixCls('workspace-panel')

// ─── 身份判断
// 仅当处于 DryRunSimulation 路由且存在 simulation_token 时，才认定为 Dry Run。
// 避免学生仿真页（/simulation）因 token 残留误判为 Dry Run，错误走 FILES_API_BASE。
const route = useRoute()
const isDryRunMode = computed(
  () => route.name === 'DryRunSimulation' && !!sessionStorage.getItem('simulation_token')
)

// ─── Shadow ROOT 模式开关
const rootFileMode = ref(false)

// ─── 学生容器路径预设（student_limited scope）
const STUDENT_PATH_PRESETS = [
  { label: '/home/student', path: '/home/student', writeable: true },
  { label: '/home', path: '/home', writeable: false },
  { label: '/root', path: '/root', writeable: false }
]
const selectedStudentPath = ref('/home/student')

// ─── 动态 API base 和根路径（根据身份 + 模式切换）
const fileApiBase = computed<string>(() => {
  if (isDryRunMode.value && rootFileMode.value) {
    return SHADOW_CONTAINER_FILES_API_BASE
  }
  if (isDryRunMode.value) {
    return FILES_API_BASE // Shadow USR = 服务器端工作区
  }
  return CONTAINER_FILES_API_BASE // 学生仿真页 = 容器 Sidecar
})

const defaultRootPath = computed<string>(() => {
  if (isDryRunMode.value && rootFileMode.value) {
    return '/' // ROOT 模式从容器根开始
  }
  if (isDryRunMode.value) {
    return '.' // USR 模式服务器端工作区相对路径
  }
  return selectedStudentPath.value // 学生模式当前预设路径
})

const rootSwitchLoading = ref(false)

function toggleRootFileMode() {
  if (rootSwitchLoading.value) return

  const nextMode = !rootFileMode.value
  console.info('[WorkspacePanel] toggleRootFileMode start', {
    from: rootFileMode.value ? 'ROOT' : 'USR',
    to: nextMode ? 'ROOT' : 'USR',
    apiBaseBefore: fileApiBase.value,
    rootPathBefore: defaultRootPath.value
  })
  const startTs = performance.now()

  rootSwitchLoading.value = true
  rootFileMode.value = nextMode
  loadTree(undefined)
    .then(() => {
      console.info('[WorkspacePanel] toggleRootFileMode done', {
        mode: rootFileMode.value ? 'ROOT' : 'USR',
        apiBaseAfter: fileApiBase.value,
        rootPathAfter: defaultRootPath.value,
        elapsedMs: Math.round(performance.now() - startTs)
      })
    })
    .catch((err) => {
      console.error('[WorkspacePanel] toggleRootFileMode failed', {
        mode: rootFileMode.value ? 'ROOT' : 'USR',
        elapsedMs: Math.round(performance.now() - startTs),
        err
      })
    })
    .finally(() => {
      rootSwitchLoading.value = false
    })
}

function selectStudentPath(path: string) {
  selectedStudentPath.value = path
  loadTree(path)
}

// ─── Props（面板集成时可传入 panelId 显示状态）
interface Props {
  panelId?: string
}
const props = defineProps<Props>()

// ─── Composables
const workspace = useWorkspace(fileApiBase, defaultRootPath)
const {
  treeData,
  loading,
  activePath,
  fileCache,
  loadTree,
  openFile,
  saveActiveFile,
  deleteCommand,
  uploadExternalCommand
} = workspace

// 兼容老逻辑的几个计算属性
const currentFile = computed(() => {
  if (!activePath.value) return null
  const fileData = fileCache[activePath.value]
  return fileData ? fileData : null
})
const saving = ref(false)

const { settings, resetSettings } = useWorkspaceSettings()
const { registerPanel, unregisterPanel, updateSettingsTree } = usePanelState()

// ─── Settings Tree
function saveSettings(newConfig: Partial<WorkspaceSettings>) {
  settings.value = { ...settings.value, ...newConfig }
}

function refreshSettingsTree() {
  if (!props.panelId) return
  updateSettingsTree(props.panelId, {
    actionHandler: createActionHandler(saveSettings, resetSettings),
    nodes: buildSettingsTree(settings.value)
  })
}

watch(
  () => settings.value,
  () => {
    if (props.panelId) refreshSettingsTree()
  },
  { deep: true }
)

// ─── 可拖拽分隔线
const splitRatio = ref(25)
const isResizing = ref(false)
const panelRef = ref<HTMLDivElement>()

function startResize(e: MouseEvent) {
  isResizing.value = true
  e.preventDefault()
}

function onMouseMove(e: MouseEvent) {
  if (!isResizing.value || !panelRef.value) return
  const rect = panelRef.value.getBoundingClientRect()
  const ratio = ((e.clientX - rect.left) / rect.width) * 100
  splitRatio.value = Math.min(Math.max(ratio, 15), 50)
}

function stopResize() {
  isResizing.value = false
}

// ─── 文件操作
async function onSave(content: string) {
  saving.value = true
  await saveActiveFile(content)
  saving.value = false
}

// ─── 顶部上传按钮
const uploaderRef = ref<HTMLInputElement>()

function triggerUpload() {
  uploaderRef.value?.click()
}

async function onFileInputChange(e: Event) {
  const input = e.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  // 上传到当前根目录
  const targetDir = defaultRootPath.value === '.' ? '.' : defaultRootPath.value
  for (const file of files) {
    await uploadExternalCommand(file, targetDir)
  }
  input.value = ''
}

// ─── 格式化
const monacoRef = ref<{ format: () => void; getValue: () => string } | null>(null)

function formatCode() {
  monacoRef.value?.format()
}

// ─── 键盘快捷键监听
function handleKeyDown(e: KeyboardEvent) {
  const target = e.target as HTMLElement
  if (target.tagName.match(/INPUT|TEXTAREA/i) || target.closest('.monaco-editor')) {
    return
  }

  const paths = Array.from(workspace.selectedPaths.value) as string[]
  if (!paths.length) return

  if (e.key === 'Delete' || e.key === 'Backspace') {
    workspace.deleteCommand(paths)
  } else if (e.key.toLowerCase() === 'c' && (e.ctrlKey || e.metaKey)) {
    workspace.copyCommand(paths)
  } else if (e.key.toLowerCase() === 'x' && (e.ctrlKey || e.metaKey)) {
    workspace.cutCommand(paths)
  } else if (e.key.toLowerCase() === 'v' && (e.ctrlKey || e.metaKey)) {
    if (paths.length === 1) {
      const node =
        workspace.treeData.value?.find((n) => n.path === paths[0]) ||
        workspace.findNodeByPath(workspace.treeData.value, paths[0])
      const targetDir = node?.type === 'directory' ? node.path : (node?.parentPath ?? '.')
      workspace.pasteCommand(targetDir)
    } else {
      workspace.pasteCommand('.')
    }
  } else if (e.key === 'F2') {
    if (paths.length === 1) workspace.startRenameCommand(paths[0])
  }
}

// ─── 脏数据拦截
function hasDirtyFiles() {
  for (const dirty of Object.values(workspace.dirtyMap)) {
    if (dirty) return true
  }
  return false
}

function onBeforeUnload(e: BeforeUnloadEvent) {
  if (hasDirtyFiles()) {
    e.preventDefault()
    e.returnValue = ''
  }
}

onBeforeRouteLeave((_to, _from, next) => {
  if (hasDirtyFiles()) {
    import('element-plus').then(({ ElMessageBox }) => {
      ElMessageBox.confirm('你有未保存的修改，离开将丢失这些修改。确实要离开吗？', '提示', {
        confirmButtonText: '离开',
        cancelButtonText: '取消',
        type: 'warning'
      })
        .then(() => next())
        .catch(() => next(false))
    })
  } else {
    next()
  }
})

// ─── 生命周期
onMounted(() => {
  if (props.panelId) {
    registerPanel(props.panelId, 'WorkspacePanel')
    refreshSettingsTree()
  }
  loadTree()
  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', stopResize)
  document.addEventListener('keydown', handleKeyDown)
  window.addEventListener('beforeunload', onBeforeUnload)
})

onUnmounted(() => {
  if (props.panelId) {
    unregisterPanel(props.panelId)
  }
  document.removeEventListener('mousemove', onMouseMove)
  document.removeEventListener('mouseup', stopResize)
  document.removeEventListener('keydown', handleKeyDown)
  window.removeEventListener('beforeunload', onBeforeUnload)
})
</script>

<template>
  <div ref="panelRef" :class="[prefixCls, isResizing && `${prefixCls}--resizing`]">
    <!-- 隐藏上传 input -->
    <input
      ref="uploaderRef"
      type="file"
      multiple
      style="display: none"
      @change="onFileInputChange"
    />

    <!-- 顶部工具栏 -->
    <div :class="`${prefixCls}__header`">
      <div :class="`${prefixCls}__header-left`">
        <Icon icon="vi-carbon:folder" />
        <span>{{ currentFile ? currentFile.name : '文件管理' }}</span>
        <span
          v-if="workspace.activePath.value && workspace.dirtyMap[workspace.activePath.value]"
          :class="`${prefixCls}__dirty`"
          title="有未保存修改"
        >
          ●
        </span>
      </div>

      <div :class="`${prefixCls}__header-right`">
        <!-- 上传 -->
        <el-tooltip content="上传文件" placement="top">
          <el-button text size="small" @click="triggerUpload">
            <Icon icon="vi-ep:upload" />
          </el-button>
        </el-tooltip>

        <!-- 格式化 -->
        <el-tooltip content="格式化代码" placement="top">
          <el-button text size="small" :disabled="!currentFile" @click="formatCode">
            <Icon icon="vi-carbon:code" />
          </el-button>
        </el-tooltip>

        <!-- Shadow 模式：USR / ROOT 切换 -->
        <el-tooltip
          v-if="isDryRunMode"
          :content="rootFileMode ? '切换回学生工作区' : '切换到容器 ROOT 文件系统'"
          placement="top"
        >
          <el-button
            text
            size="small"
            :type="rootFileMode ? 'danger' : 'default'"
            :loading="rootSwitchLoading"
            :disabled="rootSwitchLoading"
            @click="toggleRootFileMode"
          >
            <Icon icon="vi-carbon:tree-view" />
            {{ rootFileMode ? 'ROOT' : 'USR' }}
          </el-button>
        </el-tooltip>

        <!-- 学生模式：路径预设切换 -->
        <template v-if="!isDryRunMode">
          <el-tooltip
            v-for="preset in STUDENT_PATH_PRESETS"
            :key="preset.path"
            :content="preset.writeable ? '可读写' : '只读'"
            placement="top"
          >
            <el-button
              text
              size="small"
              :type="selectedStudentPath === preset.path ? 'primary' : 'default'"
              @click="selectStudentPath(preset.path)"
            >
              {{ preset.label }}
            </el-button>
          </el-tooltip>
        </template>

        <!-- 保存 -->
        <el-button
          type="primary"
          size="small"
          :loading="saving"
          :disabled="!currentFile || !workspace.dirtyMap[workspace.activePath.value!]"
          @click="onSave(currentFile?.content || '')"
        >
          <Icon icon="vi-ep:check" />
          保存
        </el-button>
      </div>
    </div>

    <!-- 主体：左树 + 分隔线 + 右编辑器 -->
    <div :class="`${prefixCls}__body`">
      <!-- 左侧文件树 -->
      <div :class="`${prefixCls}__left`" :style="{ width: `${splitRatio}%` }">
        <FileTree
          :tree-data="treeData"
          :loading="loading"
          :workspace="workspace"
          @select-file="openFile"
          @delete="(path) => deleteCommand([path])"
          @upload="uploadExternalCommand"
        />
      </div>

      <!-- 分隔拖拽线 -->
      <div :class="`${prefixCls}__divider`" @mousedown="startResize"></div>

      <!-- 右侧 新版 Editor 工作台 -->
      <div :class="`${prefixCls}__right`" :style="{ width: `${100 - splitRatio}%` }">
        <EditorWorkbench
          :preview-path="workspace.previewPath.value"
          :active-path="workspace.activePath.value"
          :pinned-tabs="workspace.pinnedTabs.value"
          :file-cache="workspace.fileCache"
          :dirty-map="workspace.dirtyMap"
          :settings="settings"
          @content-change="
            (content) => {
              if (workspace.activePath.value) {
                const active = workspace.activePath.value
                const fc = workspace.fileCache[active]
                const changed = (fc?.content ?? '') !== content
                workspace.markDirty(active, changed)
                if (fc) fc.content = content
              }
            }
          "
          @save="onSave"
          @select-tab="(path, asPreview) => workspace.openFile(path, asPreview)"
          @close-tab="workspace.closeTab"
        />
      </div>
    </div>
  </div>
</template>

<style lang="less" scoped>
@prefix: v-workspace-panel;

.@{prefix} {
  display: flex;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: var(--el-bg-color);
  user-select: none;
  flex-direction: column;

  &--resizing {
    cursor: col-resize;
  }

  &__header {
    display: flex;
    height: 40px;
    padding: 6px 12px;
    background: var(--el-bg-color-page);
    border-bottom: 1px solid var(--el-border-color);
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;

    &-left {
      display: flex;
      overflow: hidden;
      font-size: 13px;
      font-weight: 500;
      color: var(--el-text-color-primary);
      align-items: center;
      gap: 6px;

      .el-icon {
        flex-shrink: 0;
        color: var(--el-color-warning);
      }

      span {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
    }

    &-right {
      display: flex;
      align-items: center;
      gap: 4px;
      flex-shrink: 0;
    }
  }

  &__dirty {
    font-size: 16px;
    line-height: 1;
    color: var(--el-color-warning) !important;
  }

  &__body {
    flex: 1;
    display: flex;
    overflow: hidden;
  }

  &__left {
    height: 100%;
    min-width: 140px;
    overflow: hidden;
    flex-shrink: 0;
  }

  &__divider {
    width: 4px;
    height: 100%;
    cursor: col-resize;
    background: var(--el-border-color-lighter);
    transition: background 0.2s;
    flex-shrink: 0;

    &:hover,
    .@{prefix}--resizing & {
      background: var(--el-color-primary-light-5);
    }
  }

  &__right {
    height: 100%;
    min-width: 0;
    overflow: hidden;
    flex: 1;
  }
}
</style>
