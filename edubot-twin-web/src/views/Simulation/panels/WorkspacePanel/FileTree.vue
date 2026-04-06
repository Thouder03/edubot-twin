<script setup lang="ts">
/**
 * FileTree.vue — 文件树入口包装组件 (Phase 1 瘦身版)
 *
 * 现已降阶为展示与事件转发层：
 * 内部将复杂拖拽、树形选区与右键交给子组件和 Composables 处理。
 *
 * ─── 目录浏览导航 (新增) ────────────────────────────────────────
 * · currentDir     : 当前浏览目录（可双击进入子目录）
 * · initialDir     : 打开文件树时记录的初始目录（用于"回到初始目录"）
 * · `..` 条目      : 显示在列表顶端，双击返回上级目录
 * · 工具栏按钮     : 返回初始目录（home 图标）
 */
import { ref, computed, onMounted } from 'vue'
import { ElIcon, ElTooltip } from 'element-plus'
import FileTreeContainer from './FileTreeContainer.vue'
import WorkspaceContextMenu from './WorkspaceContextMenu.vue'
import { Icon } from '@/components/Icon'
import { useDesign } from '@/hooks/web/useDesign'

const { getPrefixCls } = useDesign()
const prefixCls = getPrefixCls('file-tree')

// 从顶层 useWorkspace 注入，也可以由 props 接收
const props = defineProps<{
  treeData: any[]
  loading?: boolean
  workspace: any
}>()

const emit = defineEmits<{
  'select-file': [path: string]
  delete: [path: string, name: string]
  upload: [file: File, targetPath: string]
}>()

// ─── 目录浏览导航状态 ────────────────────────────────────────────
// '.' 表示根目录（工作区根）
const initialDir = ref('.')
const currentDir = ref('.')

// 当前目录显示名（工具栏面包屑）
const currentDirLabel = computed(() => {
  if (currentDir.value === '.' || currentDir.value === '') return '~'
  // 显示最后一段目录名，保持简洁
  const parts = currentDir.value.split('/').filter(Boolean)
  return parts[parts.length - 1] ?? '~'
})

// 是否在初始目录
const isAtInitialDir = computed(() => currentDir.value === initialDir.value)

// 是否可以返回上级（不在根目录）
const canGoUp = computed(() => currentDir.value !== '.' && currentDir.value !== '')

// 取父目录路径
function getParentDir(path: string): string {
  const normalized = path.replace(/\/+$/, '')
  const slashIdx = normalized.lastIndexOf('/')
  if (slashIdx <= 0) return '.'
  return normalized.slice(0, slashIdx)
}

// 进入指定目录（双击文件夹触发）
async function navigateTo(dirPath: string) {
  // 如果该目录子节点尚未加载，先调用 workspace.refreshNode 触发懒加载
  const node = findNodeByPath(props.treeData, dirPath)
  if (node && !node.childrenLoaded) {
    await props.workspace.refreshNode(dirPath)
  }
  currentDir.value = dirPath
}

// 返回上级目录
function goUp() {
  if (!canGoUp.value) return
  currentDir.value = getParentDir(currentDir.value)
}

// 返回初始目录
function goHome() {
  currentDir.value = initialDir.value
}

// 记录初始目录（组件挂载时锁定，可由外部通过 workspace 获取）
onMounted(() => {
  // 如果 workspace 暴露了根路径则使用，否则默认 '.'
  initialDir.value = props.workspace?.rootPath?.value ?? '.'
  currentDir.value = initialDir.value
})

// ─── 过滤后的树节点（只展示当前目录的直属子节点）────────────────
// 注意：treeData 是懒加载树，currentDir 改变时对应节点可能还未加载。
// 策略：currentDir === '.' 时显示完整 treeData；进入子目录时，
//       找到对应节点并只显示其 children（可能触发懒加载）。
const filteredTreeData = computed(() => {
  if (currentDir.value === '.' || currentDir.value === '') {
    return props.treeData
  }
  const node = findNodeByPath(props.treeData, currentDir.value)
  if (!node) return props.treeData
  return node.children ?? []
})

function findNodeByPath(nodes: any[], path: string): any | null {
  for (const node of nodes) {
    if (node.path === path) return node
    if (node.children?.length) {
      const found = findNodeByPath(node.children, path)
      if (found) return found
    }
  }
  return null
}

// ─── 右键菜单组件引用 ────────────────────────────────────────────
const contextMenuRef = ref<InstanceType<typeof WorkspaceContextMenu> | null>(null)

// FileTreeContainer 组件引用，用于获取扁平可见节点列表（Shift 范围选）
const containerRef = ref<InstanceType<typeof FileTreeContainer> | null>(null)

// 多选模式快捷访问
const isMultiSelectMode = computed(() => props.workspace.multiSelectMode?.value ?? false)

function onSelectFile(path: string, event: MouseEvent) {
  const isMulti = event.metaKey || event.ctrlKey
  const isShift = event.shiftKey
  const flatPaths = isShift ? (containerRef.value?.getFlatVisiblePaths() ?? []) : []
  props.workspace.toggleSelection(path, isMulti, isShift, flatPaths)
  const node = props.workspace.findNodeByPath(props.treeData, path)
  // 目录展开由 FileTreeContainer 内部通过 he-tree addMulti API 处理
  if (!node || node.type === 'file') {
    emit('select-file', path)
  }
}

// 双击文件夹 → 进入该目录；双击文件 → 固定打开文件
function onOpenFilePinned(path: string) {
  const node = props.workspace.findNodeByPath(props.treeData, path)
  if (node && node.type === 'directory') {
    navigateTo(path)
  } else if (node && node.type === 'file') {
    props.workspace.openFile(path, false)
  }
}

function onNodeContextMenu(node: any, event: MouseEvent) {
  event.preventDefault()
  props.workspace.determineContextMenuSelection(node.path)
  contextMenuRef.value?.show(event, node)
}

function onDropExternal(files: FileList, targetPath: string) {
  Array.from(files).forEach((file) => {
    emit('upload', file, targetPath)
  })
}

function onMoveInternal(sourcePaths: string[], targetDir: string) {
  props.workspace.moveCommand(sourcePaths, targetDir)
}

async function onManualRefresh() {
  await props.workspace.refreshExpandedDirectories()
}
</script>

<template>
  <div :class="prefixCls">
    <!-- 工具栏 -->
    <div :class="`${prefixCls}__toolbar`">
      <span :class="`${prefixCls}__title`">WORKSPACE</span>
      <div :class="`${prefixCls}__toolbar-actions`">
        <!-- 多选模式切换 -->
        <el-tooltip
          :content="isMultiSelectMode ? '关闭多选模式' : '开启多选模式（可用快捷键）'"
          placement="top"
        >
          <el-icon
            :class="[`${prefixCls}__action`, isMultiSelectMode && `${prefixCls}__action--active`]"
            @click.stop="props.workspace.toggleMultiSelectMode?.()"
          >
            <Icon icon="vi-carbon:list-checked" />
          </el-icon>
        </el-tooltip>

        <!-- 刷新 -->
        <el-tooltip content="刷新文件树" placement="top">
          <el-icon :class="`${prefixCls}__action`" @click.stop="onManualRefresh">
            <Icon icon="vi-ep:refresh" />
          </el-icon>
        </el-tooltip>

        <!-- 返回初始目录 -->
        <el-tooltip content="返回初始目录" placement="top">
          <el-icon
            :class="[`${prefixCls}__action`, isAtInitialDir && `${prefixCls}__action--dimmed`]"
            @click.stop="goHome"
          >
            <Icon icon="vi-ep:house" />
          </el-icon>
        </el-tooltip>
      </div>
    </div>

    <!-- 当前目录路径面包屑 -->
    <div v-if="currentDir !== '.'" :class="`${prefixCls}__breadcrumb`">
      <el-icon :class="`${prefixCls}__breadcrumb-icon`">
        <Icon icon="vi-ep:folder-opened" />
      </el-icon>
      <span :class="`${prefixCls}__breadcrumb-label`" :title="currentDir">
        {{ currentDirLabel }}
      </span>
    </div>

    <!-- 树主体容器 -->
    <div :class="`${prefixCls}__body`">
      <!-- `..` 返回上级条目，双击返回上级目录 -->
      <div v-if="canGoUp" :class="`${prefixCls}__go-up`" @dblclick.stop="goUp">
        <el-icon :class="`${prefixCls}__go-up-icon`">
          <Icon icon="vi-ep:arrow-left-bold" />
        </el-icon>
        <span :class="`${prefixCls}__go-up-label`">.. (返回上级)</span>
      </div>

      <div :class="`${prefixCls}__tree-wrap`">
        <FileTreeContainer
          ref="containerRef"
          :tree-data="filteredTreeData"
          :loading="loading"
          :selected-paths="props.workspace.selectedPaths.value"
          @select-file="onSelectFile"
          @open-file-pinned="onOpenFilePinned"
          @node-contextmenu="onNodeContextMenu"
          @drop-external="onDropExternal"
          @move-internal="onMoveInternal"
          @rename-submit="props.workspace.renameCommand"
          @rename-cancel="props.workspace.cancelRenameCommand"
        />
      </div>
    </div>

    <!-- 右键菜单 -->
    <WorkspaceContextMenu ref="contextMenuRef" :commands="props.workspace" />
  </div>
</template>

<style lang="less" scoped>
@prefix: v-file-tree;

.@{prefix} {
  display: flex;
  width: 100%;
  height: 100%;
  background: var(--el-bg-color-page);
  border-right: 1px solid var(--el-border-color);
  flex-direction: column;

  &__toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 12px;
    border-bottom: 1px solid var(--el-border-color-lighter);
    flex-shrink: 0;
  }

  &__title {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.08em;
    color: var(--el-text-color-secondary);
  }

  &__toolbar-actions {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  &__action {
    color: var(--el-text-color-secondary);
    cursor: pointer;
    transition: color 0.2s;

    &:hover {
      color: var(--el-color-primary);
    }

    &--active {
      color: var(--el-color-primary) !important;
      background-color: var(--el-color-primary-light-9);
      border-radius: 3px;
    }

    &--dimmed {
      color: var(--el-text-color-disabled) !important;
      cursor: default;
      pointer-events: none;
    }
  }

  // 面包屑导航条
  &__breadcrumb {
    display: flex;
    align-items: center;
    padding: 4px 10px;
    gap: 5px;
    background: var(--el-fill-color-lighter);
    border-bottom: 1px solid var(--el-border-color-lighter);
    flex-shrink: 0;
  }

  &__breadcrumb-icon {
    font-size: 13px;
    color: var(--el-color-warning);
    flex-shrink: 0;
  }

  &__breadcrumb-label {
    font-size: 11px;
    font-weight: 500;
    color: var(--el-text-color-regular);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  // 树主体（含 .. 条和 FileTreeContainer）
  &__body {
    flex: 1;
    overflow: auto;
    display: flex;
    flex-direction: column;
  }

  // 树内容区（flex:1 填充）
  &__tree-wrap {
    flex: 1;
    overflow: auto;
    min-height: 0;
  }

  // `..` 返回上级条目
  &__go-up {
    display: flex;
    align-items: center;
    height: 26px;
    padding: 0 8px;
    gap: 6px;
    cursor: pointer;
    border-bottom: 1px dashed var(--el-border-color-lighter);
    flex-shrink: 0;

    &:hover {
      background: var(--el-fill-color-light);
    }
  }

  &__go-up-icon {
    font-size: 12px;
    color: var(--el-text-color-placeholder);
    flex-shrink: 0;
  }

  &__go-up-label {
    font-size: 12px;
    color: var(--el-text-color-placeholder);
    user-select: none;
  }
}
</style>
