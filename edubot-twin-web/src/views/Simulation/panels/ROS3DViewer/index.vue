<script setup lang="ts">
/**
 * ROS 3D 视图面板 - TODO 占位组件
 * 后续将集成 ros3djs
 */
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { Icon } from '@/components/Icon'
import { usePanelState } from '../../stores/panelState'
import {
  defaultConfig,
  buildSettingsTree,
  createActionHandler,
  type ROS3DViewerConfig
} from './settings'

// ---------- Props ----------
interface Props {
  panelId: string
}

const props = defineProps<Props>()

// ---------- 面板设置集成 ----------
const { registerPanel, unregisterPanel, updateSettingsTree } = usePanelState()
const config = ref<ROS3DViewerConfig>({ ...defaultConfig })

function saveConfig(newConfig: ROS3DViewerConfig) {
  config.value = newConfig
  // 更新设置树（让 PanelSettings 刷新）
  refreshSettingsTree()
}

function refreshSettingsTree() {
  updateSettingsTree(props.panelId, {
    actionHandler: createActionHandler(config.value, saveConfig),
    nodes: buildSettingsTree(config.value)
  })
}

onMounted(() => {
  registerPanel(props.panelId, 'ROS3DViewer')
  refreshSettingsTree()
})

onBeforeUnmount(() => {
  unregisterPanel(props.panelId)
})

// 配置变更时更新设置树
watch(config, refreshSettingsTree, { deep: true })
</script>

<template>
  <div class="ros3d-viewer">
    <div class="ros3d-placeholder">
      <Icon icon="vi-carbon:cube" :size="48" class="ros3d-icon" />
      <h3>ROS 3D Viewer</h3>
      <p>ros3djs 3D 可视化面板</p>
      <div class="ros3d-info">
        <span class="info-label">WebSocket:</span>
        <span class="info-value">{{ config.rosUrl }}</span>
      </div>
      <div class="ros3d-info">
        <span class="info-label">Frame:</span>
        <span class="info-value">{{ config.fixedFrame }}</span>
      </div>
      <div class="ros3d-badge">TODO: 集成 ros3djs</div>
    </div>
  </div>
</template>

<style lang="less" scoped>
.ros3d-viewer {
  width: 100%;
  height: 100%;
  background: #1e1e2e;
  display: flex;
  align-items: center;
  justify-content: center;
}

.ros3d-placeholder {
  text-align: center;
  color: #cdd6f4;

  .ros3d-icon {
    color: #89b4fa;
    margin-bottom: 12px;
  }

  h3 {
    font-size: 16px;
    font-weight: 600;
    margin-bottom: 4px;
  }

  p {
    color: #6c7086;
    font-size: 13px;
    margin-bottom: 16px;
  }

  .ros3d-info {
    font-size: 12px;
    margin-bottom: 4px;

    .info-label {
      color: #6c7086;
      margin-right: 6px;
    }

    .info-value {
      color: #a6adc8;
      font-family: monospace;
    }
  }

  .ros3d-badge {
    margin-top: 16px;
    display: inline-block;
    padding: 4px 12px;
    background: #313244;
    border-radius: 12px;
    font-size: 11px;
    color: #f9e2af;
  }
}
</style>
