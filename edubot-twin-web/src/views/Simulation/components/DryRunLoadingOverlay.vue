<script setup lang="ts">
/**
 * DryRunLoadingOverlay - Dry Run 仿真页加载覆盖层
 *
 * 全屏遮罩，仿 ElLoading 风格（暗色背景 + 旋转动画 + 阶段文字）。
 * 在 DryRunSimulation.vue 的 onMounted 中轮询容器状态，
 * 确认 running 后父组件设 v-if="false" 移除此覆盖层。
 */
defineProps<{
  stageText?: string
  isError?: boolean
}>()
</script>

<template>
  <div class="dry-run-overlay">
    <div class="overlay-body">
      <div v-if="!isError" class="spinner"></div>
      <div v-else class="error-icon">⚠️</div>
      <div class="overlay-text" :class="{ 'overlay-text--error': isError }">
        {{ stageText || '正在连接仿真容器...' }}
      </div>
      <div v-if="!isError" class="overlay-hint">Dry Run 环境初始化中，请稍候</div>
      <div v-else class="overlay-hint">可使用右下角工具栏查看 Docker Logs</div>
    </div>
  </div>
</template>

<style scoped>
.dry-run-overlay {
  position: fixed;
  inset: 0;
  /* z-index 设为 100：高于正常页面内容，但远低于 Element Plus Dialog （2000+）和工具栏（10000）
  这样工具栏弹出的对话框不会被覆盖层遮住 */
  z-index: 100;
  background: rgba(17, 17, 27, 0.96);
  display: flex;
  align-items: center;
  justify-content: center;
}

.overlay-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}

.spinner {
  width: 52px;
  height: 52px;
  border: 4px solid #313244;
  border-top-color: #cba6f7;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.overlay-text {
  color: #cdd6f4;
  font-size: 16px;
  font-weight: 500;
  letter-spacing: 0.5px;

  &--error {
    color: #f38ba8;
  }
}

.error-icon {
  font-size: 40px;
  margin-bottom: 4px;
}

.overlay-hint {
  color: #6c7086;
  font-size: 13px;
  letter-spacing: 0.3px;
}
</style>
