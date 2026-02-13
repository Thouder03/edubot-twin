<script setup lang="ts">
/**
 * GzWeb 仿真面板 - TODO 占位组件
 * 后续将嵌入 GzWeb iframe
 */
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { Icon } from '@/components/Icon'
import { usePanelState } from '../../stores/panelState'
import {
  defaultConfig,
  buildSettingsTree,
  createActionHandler,
  type GzWebViewerConfig
} from './settings'

// ---------- Props ----------
interface Props {
  panelId: string
}

const props = defineProps<Props>()

// ---------- 面板设置集成 ----------
const { registerPanel, unregisterPanel, updateSettingsTree } = usePanelState()
const config = ref<GzWebViewerConfig>({ ...defaultConfig })

function saveConfig(newConfig: GzWebViewerConfig) {
  config.value = newConfig
  refreshSettingsTree()
}

function refreshSettingsTree() {
  updateSettingsTree(props.panelId, {
    actionHandler: createActionHandler(config.value, saveConfig),
    nodes: buildSettingsTree(config.value)
  })
}

onMounted(() => {
  registerPanel(props.panelId, 'GzWebViewer')
  refreshSettingsTree()
})

onBeforeUnmount(() => {
  unregisterPanel(props.panelId)
})

watch(config, refreshSettingsTree, { deep: true })
</script>

<template>
  <div class="gzweb-viewer">
    <div class="gzweb-placeholder">
      <Icon icon="vi-carbon:model-alt" :size="48" class="gzweb-icon" />
      <h3>Gazebo Web Viewer</h3>
      <p>GzWeb 仿真环境面板</p>
      <div class="gzweb-info">
        <span class="info-label">URL:</span>
        <span class="info-value">{{ config.gzwebUrl }}</span>
      </div>
      <div class="gzweb-badge">TODO: 嵌入 GzWeb iframe</div>
    </div>
  </div>
</template>

<style lang="less" scoped>
.gzweb-viewer {
  width: 100%;
  height: 100%;
  background: #1e1e2e;
  display: flex;
  align-items: center;
  justify-content: center;
}

.gzweb-placeholder {
  text-align: center;
  color: #cdd6f4;

  .gzweb-icon {
    color: #a6e3a1;
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

  .gzweb-info {
    font-size: 12px;

    .info-label {
      color: #6c7086;
      margin-right: 6px;
    }

    .info-value {
      color: #a6adc8;
      font-family: monospace;
    }
  }

  .gzweb-badge {
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
