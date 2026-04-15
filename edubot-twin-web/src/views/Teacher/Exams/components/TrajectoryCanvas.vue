<template>
  <div class="trajectory-canvas-wrap">
    <div v-if="error" class="trajectory-error">
      <el-alert type="warning" :title="error" :closable="false" />
    </div>
    <div v-else-if="!data" class="trajectory-empty">
      <el-skeleton animated :rows="4" />
    </div>
    <canvas v-else ref="canvasRef" class="trajectory-canvas"></canvas>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, nextTick } from 'vue'

interface TrajectoryPoint {
  t: number
  x: number
  y: number
  theta?: number
}
interface CollisionPoint {
  t: number
  x: number
  y: number
}
interface TrajectoryData {
  points: TrajectoryPoint[]
  start?: { x: number; y: number }
  goal?: { x: number; y: number }
  collisions?: CollisionPoint[]
}

const props = defineProps<{
  data: TrajectoryData | null
  error?: string | null
}>()

const canvasRef = ref<HTMLCanvasElement | null>(null)

watch(
  () => props.data,
  () => {
    nextTick(render)
  }
)
onMounted(() => {
  if (props.data) nextTick(render)
})

function render() {
  const canvas = canvasRef.value
  const data = props.data
  if (!canvas || !data || data.points.length === 0) return

  const W = canvas.offsetWidth || 600
  const H = 320
  canvas.width = W
  canvas.height = H
  const ctx = canvas.getContext('2d')!
  const PAD = 40

  // 计算坐标范围
  const allX = data.points.map((p) => p.x)
  const allY = data.points.map((p) => p.y)
  if (data.start) {
    allX.push(data.start.x)
    allY.push(data.start.y)
  }
  if (data.goal) {
    allX.push(data.goal.x)
    allY.push(data.goal.y)
  }
  ;(data.collisions ?? []).forEach((c) => {
    allX.push(c.x)
    allY.push(c.y)
  })

  const minX = Math.min(...allX),
    maxX = Math.max(...allX)
  const minY = Math.min(...allY),
    maxY = Math.max(...allY)
  const rangeX = maxX - minX || 1,
    rangeY = maxY - minY || 1

  const sx = (W - PAD * 2) / rangeX
  const sy = (H - PAD * 2) / rangeY
  const scale = Math.min(sx, sy)
  const offX = PAD + (W - PAD * 2 - rangeX * scale) / 2
  const offY = PAD + (H - PAD * 2 - rangeY * scale) / 2

  const toCanvas = (x: number, y: number) => ({
    cx: offX + (x - minX) * scale,
    cy: H - (offY + (y - minY) * scale) // Y 轴翻转
  })

  // 背景
  ctx.fillStyle = '#1a1a2e'
  ctx.fillRect(0, 0, W, H)

  // 轨迹折线
  ctx.beginPath()
  ctx.strokeStyle = '#4fc3f7'
  ctx.lineWidth = 2
  data.points.forEach((p, i) => {
    const { cx, cy } = toCanvas(p.x, p.y)
    i === 0 ? ctx.moveTo(cx, cy) : ctx.lineTo(cx, cy)
  })
  ctx.stroke()

  // 起点 S
  if (data.start) {
    const { cx, cy } = toCanvas(data.start.x, data.start.y)
    ctx.fillStyle = '#4caf50'
    ctx.beginPath()
    ctx.arc(cx, cy, 7, 0, Math.PI * 2)
    ctx.fill()
    ctx.fillStyle = '#fff'
    ctx.font = 'bold 10px sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText('S', cx, cy)
  }

  // 终点 G
  if (data.goal) {
    const { cx, cy } = toCanvas(data.goal.x, data.goal.y)
    ctx.fillStyle = '#8bc34a'
    ctx.beginPath()
    ctx.arc(cx, cy, 7, 0, Math.PI * 2)
    ctx.fill()
    ctx.fillStyle = '#fff'
    ctx.font = 'bold 10px sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText('G', cx, cy)
  }

  // 碰撞点
  ;(data.collisions ?? []).forEach((c) => {
    const { cx, cy } = toCanvas(c.x, c.y)
    ctx.fillStyle = '#f44336'
    ctx.beginPath()
    ctx.arc(cx, cy, 5, 0, Math.PI * 2)
    ctx.fill()
  })
}
</script>

<style scoped>
.trajectory-canvas-wrap {
  width: 100%;
}
.trajectory-canvas {
  width: 100%;
  height: 320px;
  border-radius: 6px;
  display: block;
}
.trajectory-error,
.trajectory-empty {
  padding: 8px 0;
}
</style>
