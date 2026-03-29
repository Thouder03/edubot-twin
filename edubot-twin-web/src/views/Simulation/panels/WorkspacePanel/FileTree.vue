<script setup lang="ts">
/**
 * FileTree.vue — 文件树组件
 *
 * 使用 el-tree 展示工作区文件层级，支持：
 * - 懒加载子目录
 * - 右键菜单（删除、新建目录）
 * - 拖拽上传
 * - 文件图标按类型显示
 */
import { ref } from 'vue'
import { ElTree, ElIcon, ElTooltip, ElDialog, ElInput, ElButton, ElMessage } from 'element-plus'
import type { TreeNode } from '@/api/files/types'
import { useDesign } from '@/hooks/web/useDesign'

const { getPrefixCls } = useDesign()
const prefixCls = getPrefixCls('file-tree')

interface Props {
  treeData: TreeNode[]
  loading?: boolean
  // 使用 any 跳过 el-tree LoadFunction 类型约束（运行时实际传递 TreeNode）
  loadChildren: (node: any, resolve: (children: TreeNode[]) => void) => void
}

const props = withDefaults(defineProps<Props>(), {
  loading: false
})

const emit = defineEmits<{
  'select-file': [path: string]
  delete: [path: string, name: string]
  mkdir: [path: string]
  upload: [file: File, targetPath: string]
}>()

// ─── 右键菜单
const contextMenu = ref({
  visible: false,
  x: 0,
  y: 0,
  node: null as TreeNode | null
})

function onNodeContextMenu(e: MouseEvent, data: TreeNode) {
  e.preventDefault()
  contextMenu.value = {
    visible: true,
    x: e.clientX,
    y: e.clientY,
    node: data
  }
}

function closeContextMenu() {
  contextMenu.value.visible = false
}

// ─── 文件图标
const FILE_ICON_MAP: Record<string, string> = {
  '.py': 'vi-vscode-icons:file-type-python',
  '.cpp': 'vi-vscode-icons:file-type-cpp',
  '.c': 'vi-vscode-icons:file-type-c',
  '.h': 'vi-vscode-icons:file-type-c',
  '.hpp': 'vi-vscode-icons:file-type-cpp',
  '.json': 'vi-vscode-icons:file-type-json',
  '.yaml': 'vi-vscode-icons:file-type-yaml',
  '.yml': 'vi-vscode-icons:file-type-yaml',
  '.xml': 'vi-vscode-icons:file-type-xml',
  '.launch': 'vi-vscode-icons:file-type-xml',
  '.sh': 'vi-vscode-icons:file-type-shell',
  '.md': 'vi-vscode-icons:file-type-markdown',
  '.txt': 'vi-carbon:document',
  '.urdf': 'vi-carbon:document',
  default: 'vi-carbon:document'
}

function getFileIcon(ext?: string): string {
  if (!ext) return FILE_ICON_MAP.default
  return FILE_ICON_MAP[ext] ?? FILE_ICON_MAP.default
}

// ─── 新建目录弹窗
const showMkdirDialog = ref(false)
const mkdirName = ref('')
const mkdirParentPath = ref('.')

function openMkdirDialog(parentPath: string) {
  mkdirParentPath.value = parentPath
  mkdirName.value = ''
  showMkdirDialog.value = true
  closeContextMenu()
}

function confirmMkdir() {
  if (!mkdirName.value.trim()) {
    ElMessage.warning('目录名不能为空')
    return
  }
  const fullPath =
    mkdirParentPath.value === '.' ? mkdirName.value : `${mkdirParentPath.value}/${mkdirName.value}`
  emit('mkdir', fullPath)
  showMkdirDialog.value = false
}

// ─── 拖拽上传
const isDragOver = ref(false)

function onDragOver(e: DragEvent) {
  e.preventDefault()
  isDragOver.value = true
}

function onDragLeave() {
  isDragOver.value = false
}

function onDrop(e: DragEvent, targetNode?: TreeNode) {
  e.preventDefault()
  isDragOver.value = false
  const files = Array.from(e.dataTransfer?.files ?? [])
  if (!files.length) return

  const targetPath = targetNode?.type === 'directory' ? targetNode.path : '.'

  for (const file of files) {
    emit('upload', file, targetPath)
  }
}

// ─── 节点点击
function onNodeClick(data: TreeNode) {
  if (data.type === 'file') {
    emit('select-file', data.path)
  }
}

// ─── 右键删除（封装为方法，避免模板内多语句编译错误）
function onContextDeleteClick() {
  if (!contextMenu.value.node) return
  emit('delete', contextMenu.value.node.path, contextMenu.value.node.label)
  closeContextMenu()
}
</script>

<template>
  <div
    :class="[prefixCls, isDragOver && `${prefixCls}--dragover`]"
    @dragover="onDragOver"
    @dragleave="onDragLeave"
    @drop="onDrop($event)"
    @click="closeContextMenu"
  >
    <!-- 工具栏 -->
    <div :class="`${prefixCls}__toolbar`">
      <span :class="`${prefixCls}__title`">WORKSPACE</span>
      <el-tooltip content="新建根目录" placement="top">
        <el-icon :class="`${prefixCls}__action`" @click.stop="openMkdirDialog('.')">
          <i class="vi-ep:folder-add"></i>
        </el-icon>
      </el-tooltip>
    </div>

    <!-- 加载态 -->
    <div v-if="loading" :class="`${prefixCls}__loading`">
      <el-icon class="is-loading"><i class="vi-ep:loading"></i></el-icon>
    </div>

    <!-- 空态 -->
    <div v-else-if="!treeData.length" :class="`${prefixCls}__empty`">
      <el-icon :size="32"><i class="vi-carbon:folder"></i></el-icon>
      <p>工作区为空</p>
      <p class="hint">拖拽文件到此处上传</p>
    </div>

    <!-- 文件树 -->
    <el-tree
      v-else
      :data="treeData"
      :props="{ isLeaf: 'isLeaf', children: 'children', label: 'label' }"
      :load="loadChildren"
      lazy
      node-key="key"
      :expand-on-click-node="false"
      :class="`${prefixCls}__tree`"
      @node-click="onNodeClick"
      @node-contextmenu="onNodeContextMenu"
    >
      <template #default="{ node: treeNode, data }">
        <div :class="`${prefixCls}__node`" @drop.stop="onDrop($event, data)">
          <!-- 图标 -->
          <el-icon :class="`${prefixCls}__node-icon`">
            <i
              v-if="data.type === 'directory'"
              :class="treeNode.expanded ? 'vi-ep:folder-opened' : 'vi-ep:folder'"
            ></i>
            <i v-else :class="getFileIcon(data.extension)"></i>
          </el-icon>

          <!-- 文件名 -->
          <span :class="`${prefixCls}__node-label`">{{ data.label }}</span>

          <!-- 操作按钮（hover 显示）-->
          <div :class="`${prefixCls}__node-actions`">
            <el-tooltip v-if="data.type === 'directory'" content="新建子目录" placement="top">
              <el-icon :size="13" @click.stop="openMkdirDialog(data.path)">
                <i class="vi-ep:folder-add"></i>
              </el-icon>
            </el-tooltip>
            <el-tooltip content="删除" placement="top">
              <el-icon
                :size="13"
                class="danger"
                @click.stop="emit('delete', data.path, data.label)"
              >
                <i class="vi-ep:delete"></i>
              </el-icon>
            </el-tooltip>
          </div>
        </div>
      </template>
    </el-tree>

    <!-- 右键菜单 -->
    <teleport to="body">
      <transition name="el-zoom-in-top">
        <div
          v-if="contextMenu.visible"
          :class="`${prefixCls}__context-menu`"
          :style="{ top: `${contextMenu.y}px`, left: `${contextMenu.x}px` }"
          @click.stop
        >
          <div
            v-if="contextMenu.node?.type === 'directory'"
            :class="`${prefixCls}__context-item`"
            @click="openMkdirDialog(contextMenu.node!.path)"
          >
            <el-icon><i class="vi-ep:folder-add"></i></el-icon>
            新建子目录
          </div>
          <div
            :class="`${prefixCls}__context-item ${prefixCls}__context-item--danger`"
            @click="onContextDeleteClick"
          >
            <el-icon><i class="vi-ep:delete"></i></el-icon>
            删除
          </div>
        </div>
      </transition>
    </teleport>

    <!-- 新建目录弹窗 -->
    <el-dialog v-model="showMkdirDialog" title="新建目录" width="320px" :append-to-body="true">
      <el-input v-model="mkdirName" placeholder="目录名" autofocus @keyup.enter="confirmMkdir" />
      <template #footer>
        <el-button @click="showMkdirDialog = false">取消</el-button>
        <el-button type="primary" @click="confirmMkdir">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style lang="less" scoped>
@prefix: v-file-tree;

.@{prefix} {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color-page);
  border-right: 1px solid var(--el-border-color);
  position: relative;
  transition: outline 0.2s;

  &--dragover {
    outline: 2px dashed var(--el-color-primary);
    outline-offset: -4px;
  }

  &__toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 12px;
    border-bottom: 1px solid var(--el-border-color-lighter);
  }

  &__title {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.08em;
    color: var(--el-text-color-secondary);
  }

  &__action {
    cursor: pointer;
    color: var(--el-text-color-secondary);
    transition: color 0.2s;

    &:hover {
      color: var(--el-color-primary);
    }
  }

  &__loading,
  &__empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 8px;
    height: 120px;
    color: var(--el-text-color-secondary);
    font-size: 13px;

    p {
      margin: 0;
    }

    .hint {
      font-size: 11px;
      color: var(--el-text-color-placeholder);
    }
  }

  &__tree {
    flex: 1;
    overflow: auto;
    padding: 4px 0;

    :deep(.el-tree-node__content) {
      height: 28px;
      border-radius: 4px;
      margin: 1px 4px;

      &:hover {
        background: var(--el-fill-color-light);
      }
    }
  }

  &__node {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 6px;
    overflow: hidden;
    min-width: 0;

    &-icon {
      flex-shrink: 0;
      font-size: 14px;
    }

    &-label {
      flex: 1;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 13px;
    }

    &-actions {
      display: none;
      align-items: center;
      gap: 4px;
      flex-shrink: 0;

      .el-icon {
        cursor: pointer;
        color: var(--el-text-color-secondary);
        padding: 2px;
        border-radius: 3px;

        &:hover {
          background: var(--el-fill-color);
          color: var(--el-color-primary);
        }

        &.danger:hover {
          color: var(--el-color-danger);
        }
      }
    }
  }

  // hover 时显示操作按钮
  :deep(.el-tree-node__content:hover) .v-file-tree__node-actions {
    display: flex;
  }

  &__context-menu {
    position: fixed;
    z-index: 9999;
    background: var(--el-bg-color-overlay);
    border: 1px solid var(--el-border-color-light);
    border-radius: 6px;
    box-shadow: var(--el-box-shadow-light);
    padding: 4px;
    min-width: 150px;
  }

  &__context-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 10px;
    font-size: 13px;
    border-radius: 4px;
    cursor: pointer;
    color: var(--el-text-color-primary);
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
