<script setup lang="ts">
/**
 * WorkspacePanel/index.vue — 工作区面板（左右分栏）
 *
 * 左侧: FileTree（文件树）
 * 右侧: MonacoEditor（代码编辑器）
 *
 * 可作为仿真页面 Golden Layout 面板，也可内嵌到独立页面。
 */
import { onMounted, ref, computed, onUnmounted, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { ElButton, ElTooltip } from 'element-plus'
import FileTree from './FileTree.vue'
import EditorWorkbench from './EditorWorkbench.vue'
import { useWorkspace } from './composables/useWorkspace'
import { useWorkspaceSettings, type WorkspaceSettings } from '@/composables/useWorkspaceSettings'
import { useDesign } from '@/hooks/web/useDesign'
import { Icon } from '@/components/Icon'
import { usePanelState } from '@/views/Simulation/stores/panelState'
import { buildSettingsTree, createActionHandler } from './settings'

const { getPrefixCls } = useDesign()
const prefixCls = getPrefixCls('workspace-panel')

// ─── Props（面板集成时可传入 panelId 显示状态）
interface Props {
  panelId?: string
}
const props = defineProps<Props>()

// ─── Composables
const workspace = useWorkspace()
// 为了保持局部名称简短，解构需要的字段
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
const splitRatio = ref(25) // 左侧宽度百分比
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
  for (const file of files) {
    await uploadExternalCommand(file, '.')
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
  // 如果焦点在输入框内部（如重命名 input，或者 Monaco Editor），不拦截快捷键
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
      // 找到选中项的父路径或者如果在目录上就贴到目录里
      const node =
        workspace.treeData.value?.find((n) => n.path === paths[0]) ||
        workspace.findNodeByPath(workspace.treeData.value, paths[0])
      const targetDir = node?.type === 'directory' ? node.path : (node?.parentPath ?? '.')
      workspace.pasteCommand(targetDir)
    } else {
      // 如果多选，默认贴到根目录
      workspace.pasteCommand('.')
    }
  } else if (e.key === 'F2') {
    if (paths.length === 1) workspace.startRenameCommand(paths[0])
  }
}

// ─── 脏数据拦截 (Dirty Data Guard)
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
        .then(() => {
          next()
        })
        .catch(() => {
          next(false) // cancel
        })
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
  window.addEventListener('beforeunload', onBeforeUnload)
})

onUnmounted(() => {
  if (props.panelId) {
    unregisterPanel(props.panelId)
  }
  document.removeEventListener('mousemove', onMouseMove)
  document.removeEventListener('mouseup', stopResize)
  window.removeEventListener('beforeunload', onBeforeUnload)
})
</script>

<template>
  <div
    ref="panelRef"
    :class="[prefixCls, isResizing && `${prefixCls}--resizing`]"
    tabindex="-1"
    @keydown="handleKeyDown"
  >
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
          @mkdir="() => {}"
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
          @content-change="
            (content) => {
              if (workspace.activePath.value) {
                const active = workspace.activePath.value
                const fc = workspace.fileCache[active]
                const changed = (fc?.content ?? '') !== content
                console.log('[Workspace/DirtyCheck]', {
                  path: active,
                  changed,
                  oldLength: (fc?.content ?? '').length,
                  newLength: content.length
                })
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
