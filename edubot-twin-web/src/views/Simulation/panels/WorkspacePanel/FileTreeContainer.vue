<script setup lang="ts">
import { ref } from 'vue'
import { Draggable, dragContext } from '@he-tree/vue'
import '@he-tree/vue/style/default.css'
import FileTreeNodeRenderer from './FileTreeNodeRenderer.vue'
import { useDesign } from '@/hooks/web/useDesign'
import { listFiles } from '@/api/files'
import { ElMessage } from 'element-plus'

const { getPrefixCls } = useDesign()
const prefixCls = getPrefixCls('file-tree-container')

const props = defineProps<{
  treeData: any[]
  loading?: boolean
  selectedPaths: Set<string>
}>()

const emit = defineEmits<{
  'select-file': [path: string, event: MouseEvent]
  'open-file-pinned': [path: string]
  'node-contextmenu': [data: any, event: MouseEvent]
  'drop-external': [files: FileList, targetPath: string]
  'move-internal': [sourcePaths: string[], targetDir: string]
  'rename-submit': [path: string, newName: string]
  'rename-cancel': [path: string]
}>()

// ─── he-tree Draggable 组件实例，用于调用 add/addMulti 等 API
const draggableRef = ref<InstanceType<typeof Draggable> | null>(null)

// ─── he-tree: 控制某个节点能否成为拖放目标
function checkDroppable(stat: any) {
  const node = stat?.data ?? stat
  if (node && node.type === 'file') return false
  return true
}

// ─── he-tree: after-drop 无参数，从 dragContext 读取拖拽信息
function getParentDir(path: string): string {
  const normalizedPath = path.replace(/\/+$/, '')
  const slashIndex = normalizedPath.lastIndexOf('/')
  if (slashIndex === -1) return '.'
  return normalizedPath.slice(0, slashIndex) || '.'
}

function getHoveredUploadTarget(eventTarget: EventTarget | null) {
  const element = eventTarget instanceof HTMLElement ? eventTarget : null
  const nodeElement = element?.closest?.('[data-node-path]') as HTMLElement | null
  const hoveredPath = nodeElement?.dataset.nodePath ?? null
  const hoveredType = nodeElement?.dataset.nodeType ?? null
  const hoveredExpanded = nodeElement?.dataset.nodeExpanded === 'true'
  const resolvedTargetPath = hoveredType === 'directory' && hoveredPath ? hoveredPath : '.'

  return {
    nodeElement,
    hoveredPath,
    hoveredType,
    hoveredExpanded,
    resolvedTargetPath
  }
}

function onTreeAfterDrop() {
  const dragNode = dragContext.dragNode
  const targetInfo = dragContext.targetInfo

  if (!dragNode?.data) return

  const dragData = dragNode.data
  const sourcePath: string | undefined = dragData.path
  if (!sourcePath) return

  const parentStat = targetInfo?.parent ?? null
  const targetDir = parentStat?.data?.path ?? '.'
  const sourceParentDir: string = dragData.parentPath || getParentDir(sourcePath)

  // 同目录内的排序不发起后端请求
  if (sourceParentDir === targetDir) {
    return
  }

  emit('move-internal', [sourcePath], targetDir)
}

// ─── 构建节点数据（与 useWorkspaceTreeState.buildTreeNodes 保持一致）
function buildNodes(directories: any[], files: any[], parentPath: string): any[] {
  const nodes: any[] = []
  for (const dir of directories) {
    nodes.push({
      key: dir.path,
      label: dir.name,
      name: dir.name,
      type: 'directory',
      path: dir.path,
      parentPath,
      isLeaf: false,
      children: [],
      childrenLoaded: false,
      isExpanded: false
    })
  }
  for (const file of files) {
    nodes.push({
      key: file.path,
      label: file.name,
      name: file.name,
      type: 'file',
      path: file.path,
      parentPath,
      extension: file.extension,
      size: file.size,
      mtime: file.modified,
      isLeaf: true
    })
  }
  return nodes
}

// ─── 懒加载并通过 he-tree API 插入子节点
async function loadAndInsert(node: any, stat: any) {
  if (node.childrenLoaded || !draggableRef.value) return
  node.isLoading = true
  try {
    const res = await listFiles(node.path)
    if (res.code === 0 && res.data) {
      const children = buildNodes(res.data.directories, res.data.files, node.path)
      node.children = children
      node.childrenLoaded = true
      // ⚠️ 关键：通过 he-tree 的 addMulti API 将子节点插入内部 Stat 树
      // 直接修改 node.children 数组对 he-tree 无效，必须通过组件 API
      if (children.length > 0) {
        draggableRef.value.addMulti(children, stat, 0)
      }
    }
  } catch (e: any) {
    ElMessage.error(`加载目录失败: ${e.message ?? e}`)
  } finally {
    node.isLoading = false
  }
}

// ─── 节点点击事件（携带原始 MouseEvent，用于 Ctrl/Shift 多选）
function onNodeClick(node: any, stat: any, event: MouseEvent) {
  if (node.type === 'directory') {
    const nextOpen = !node.isExpanded
    node.isExpanded = nextOpen
    stat.open = nextOpen
    if (nextOpen && !node.childrenLoaded) {
      loadAndInsert(node, stat)
    }
  } else {
    emit('select-file', node.path, event)
  }
}

// ─── 箭头图标点击
function onToggleExpandFromArrow(node: any, stat: any) {
  const nextOpen = !node.isExpanded
  node.isExpanded = nextOpen
  stat.open = nextOpen
  if (nextOpen && !node.childrenLoaded) {
    loadAndInsert(node, stat)
  }
}

// ─── 外部文件拖入（OS 文件系统）
const isDragOver = ref(false)

function isExternalFileDrag(e: DragEvent) {
  return !!e.dataTransfer?.types?.includes('Files')
}

function setCopyDropEffect(e: DragEvent) {
  e.preventDefault()
  if (e.dataTransfer) {
    e.dataTransfer.dropEffect = 'copy'
  }
}

function onDragEnterCapture(e: DragEvent) {
  if (!isExternalFileDrag(e)) return
  setCopyDropEffect(e)
}

function onDragOverCapture(e: DragEvent) {
  if (!isExternalFileDrag(e)) return
  setCopyDropEffect(e)
}

function onDragOver(e: DragEvent) {
  if (!isExternalFileDrag(e)) return
  setCopyDropEffect(e)
  isDragOver.value = true
}

function onDragLeave() {
  isDragOver.value = false
}

function ensureDirectoryVisibleAfterUpload(
  hoveredTarget: ReturnType<typeof getHoveredUploadTarget>
) {
  if (hoveredTarget.hoveredType !== 'directory') return
  if (hoveredTarget.hoveredExpanded) return
  hoveredTarget.nodeElement?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
}

function onDrop(e: DragEvent) {
  isDragOver.value = false
  const files = e.dataTransfer?.files
  if (files && files.length > 0) {
    setCopyDropEffect(e)
    const hoveredTarget = getHoveredUploadTarget(e.target)
    ensureDirectoryVisibleAfterUpload(hoveredTarget)
    emit('drop-external', files, hoveredTarget.resolvedTargetPath)
  }
}

// ─── 获取当前可见的扁平节点路径列表（用于 Shift 范围选择）
function getFlatVisiblePaths(): string[] {
  const result: string[] = []
  function walk(nodes: any[]) {
    for (const node of nodes) {
      result.push(node.path)
      if (node.type === 'directory' && node.isExpanded && Array.isArray(node.children)) {
        walk(node.children)
      }
    }
  }
  walk(props.treeData)
  return result
}

defineExpose({ getFlatVisiblePaths })
</script>

<template>
  <div
    :class="[prefixCls, isDragOver && `${prefixCls}--dragover`]"
    @dragenter.capture="onDragEnterCapture"
    @dragover.capture="onDragOverCapture"
    @dragover="onDragOver"
    @dragleave="onDragLeave"
    @drop="onDrop"
  >
    <div v-if="loading" :class="`${prefixCls}__loading`"> Loading... </div>

    <Draggable
      v-else
      ref="draggableRef"
      :model-value="treeData"
      :indent="0"
      :each-droppable="checkDroppable"
      @after-drop="onTreeAfterDrop"
      class="he-tree"
    >
      <template #default="{ node, stat }">
        <!--
          ⚠️ 绝对不能在这里加 .stop 修饰符！
             .stop 会阻止冒泡，导致 he-tree 内部 click 包装层收不到事件，
             @click:node 将永远不触发。
        -->
        <FileTreeNodeRenderer
          :node="node"
          :stat="stat"
          :is-selected="selectedPaths.has(node.path)"
          @click="(e) => onNodeClick(node, stat, e)"
          @dblclick="emit('open-file-pinned', node.path)"
          @contextmenu.prevent="emit('node-contextmenu', node, $event)"
          @toggle-expand="onToggleExpandFromArrow(node, stat)"
          @rename-submit="(newName: string) => emit('rename-submit', node.path, newName)"
          @rename-cancel="emit('rename-cancel', node.path)"
        />
      </template>
    </Draggable>
  </div>
</template>

<style lang="less" scoped>
@prefix: v-file-tree-container;

.@{prefix} {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: auto;

  &--dragover::after {
    position: absolute;
    pointer-events: none;
    border: 2px dashed var(--el-color-primary);
    content: '';
    inset: 2px;
  }
}
</style>
