<script setup lang="ts">
import { useDesign } from '@/hooks/web/useDesign'
import { useCamera } from './composables/useCamera'
import { ElButton } from 'element-plus'

const props = defineProps<{ panelId: string }>()

const { getPrefixCls } = useDesign()
const prefixCls = getPrefixCls('camera-panel')

const { imageSrc, paused, rosConnected, fps, isRunning, statusText, screenshot, reconnect } =
  useCamera(props.panelId)
</script>

<template>
  <div :class="prefixCls">
    <div v-if="!isRunning" :class="`${prefixCls}__overlay`">
      <div :class="`${prefixCls}__overlay-icon`">⚠</div>
      <div :class="`${prefixCls}__overlay-text`">{{ statusText }}</div>
    </div>

    <template v-else>
      <div :class="`${prefixCls}__topbar`">
        <div :class="`${prefixCls}__status`">
          <span
            :class="[
              `${prefixCls}__dot`,
              rosConnected ? `${prefixCls}__dot--ok` : `${prefixCls}__dot--off`
            ]"
          ></span>
          <span>{{ rosConnected ? 'ROS 已连接' : 'ROS 未连接' }}</span>
          <span :class="`${prefixCls}__fps`">FPS: {{ fps }}</span>
        </div>

        <div :class="`${prefixCls}__actions`">
          <el-button size="small" @click="paused = !paused">{{
            paused ? '恢复' : '暂停'
          }}</el-button>
          <el-button size="small" @click="reconnect">刷新</el-button>
          <el-button size="small" type="primary" :disabled="!imageSrc" @click="screenshot">
            截图
          </el-button>
        </div>
      </div>

      <div :class="`${prefixCls}__body`">
        <img v-if="imageSrc" :src="imageSrc" :class="`${prefixCls}__image`" alt="camera-frame" />
        <div v-else :class="`${prefixCls}__placeholder`">暂无图像数据</div>
        <div v-if="paused" :class="`${prefixCls}__paused`">已暂停</div>
      </div>
    </template>
  </div>
</template>

<style scoped lang="less">
@prefix: v-camera-panel;

.@{prefix} {
  position: relative;
  display: flex;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: #0f172a;
  flex-direction: column;

  &__overlay {
    position: absolute;
    z-index: 10;
    display: flex;
    background: rgb(15 23 42 / 90%);
    inset: 0;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 10px;
  }

  &__overlay-icon {
    font-size: 30px;
    color: #facc15;
  }

  &__overlay-text {
    font-size: 14px;
    color: #cbd5e1;
  }

  &__topbar {
    display: flex;
    padding: 8px 10px;
    color: #e2e8f0;
    background: rgb(15 23 42 / 85%);
    border-bottom: 1px solid rgb(148 163 184 / 20%);
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }

  &__status {
    display: flex;
    font-size: 12px;
    align-items: center;
    gap: 8px;
  }

  &__dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;

    &--ok {
      background: #22c55e;
    }

    &--off {
      background: #ef4444;
    }
  }

  &__fps {
    color: #93c5fd;
  }

  &__actions {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  &__body {
    position: relative;
    display: flex;
    overflow: hidden;
    flex: 1;
    align-items: center;
    justify-content: center;
  }

  &__image {
    width: 100%;
    height: 100%;
    object-fit: contain;
    background: #020617;
  }

  &__placeholder {
    font-size: 14px;
    color: #94a3b8;
  }

  &__paused {
    position: absolute;
    top: 12px;
    right: 12px;
    padding: 4px 8px;
    font-size: 12px;
    color: #f8fafc;
    background: rgb(15 23 42 / 80%);
    border: 1px solid rgb(148 163 184 / 35%);
    border-radius: 4px;
  }
}
</style>
