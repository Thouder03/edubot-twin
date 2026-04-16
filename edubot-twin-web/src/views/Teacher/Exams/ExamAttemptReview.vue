<template>
  <div class="exam-attempt-review">
    <!-- 顶部导航 -->
    <div class="review-header">
      <el-button :icon="Back" @click="router.back()">返回</el-button>
      <div class="header-title">
        <span class="title-main">考试复核</span>
        <span v-if="attempt" class="title-sub">
          {{ attempt.student.real_name || attempt.student.username }}
          &nbsp;/&nbsp;{{ attempt.exam.name }} &nbsp;#{{ attempt.attempt_id }}
        </span>
        <el-tag v-if="attempt" :type="statusTagType(attempt.status)" size="small" class="ml-8">
          {{ statusLabel(attempt.status) }}
        </el-tag>
      </div>
      <!-- 第14期：查看提交代码入口 -->
      <el-button
        v-if="attempt?.submission_snapshot_path"
        type="primary"
        plain
        size="small"
        @click="router.push(`/teacher/exams/attempts/${attemptId}/submission`)"
      >
        📂 查看提交代码
      </el-button>
    </div>

    <div v-if="loading" class="page-loading">
      <el-skeleton :rows="10" animated />
    </div>

    <div v-else-if="loadError" class="page-error">
      <el-result icon="error" :title="loadError" />
    </div>

    <template v-else-if="attempt">
      <!-- 分数概览 -->
      <section class="review-section">
        <ScoreOverview :attempt="attempt" />
      </section>

      <!-- 主体两栏 -->
      <div class="review-body">
        <!-- 左栏：指标 + artifacts + 轨迹图 -->
        <div class="review-col-left">
          <el-card class="review-card">
            <template #header>
              <span>📈 指标摘要</span>
            </template>
            <MetricsSummary :attempt="attempt" />
          </el-card>

          <el-card class="review-card">
            <template #header>
              <span>📂 Artifacts</span>
            </template>
            <ArtifactsExplorer
              :tree="artifactsTree"
              @preview="openPreview"
              @view-trajectory="openTrajectory"
            />
          </el-card>

          <el-card v-if="trajectoryData" class="review-card">
            <template #header>
              <span>🗺️ 轨迹图</span>
            </template>
            <TrajectoryCanvas :data="trajectoryData" :error="trajectoryError" />
          </el-card>
        </div>

        <!-- 右栏：人工评分 + 覆盖 -->
        <div class="review-col-right">
          <el-card class="review-card">
            <template #header>
              <span>📝 人工评分</span>
              <el-tag
                v-if="attempt.review_status === 'reviewed'"
                type="success"
                size="small"
                class="ml-8"
              >
                已评分
              </el-tag>
            </template>
            <div v-if="!canSubmitScore" class="score-blocked">
              <el-alert
                type="info"
                :title="`当前状态「${statusLabel(attempt.status)}」不支持提交人工评分`"
                :closable="false"
              />
            </div>
            <ManualScoreForm v-else :attempt="attempt" @submitted="handleScoreSubmitted" />
            <ScoreOverrideDrawer :attempt="attempt" @overridden="handleOverridden" />
          </el-card>
        </div>
      </div>

      <!-- 生命周期时间轴 -->
      <el-card class="review-card mt-16">
        <template #header>
          <span>📅 生命周期事件</span>
        </template>
        <LifecycleTimeline :events="events" />
      </el-card>
    </template>

    <!-- 文件预览弹窗 -->
    <ArtifactPreviewDialog
      v-model="previewDialogVisible"
      :attempt-id="attempt?.attempt_id ?? null"
      :filename="previewFilename"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Back } from '@element-plus/icons-vue'

import ScoreOverview from './components/ScoreOverview.vue'
import MetricsSummary from './components/MetricsSummary.vue'
import ArtifactsExplorer from './components/ArtifactsExplorer.vue'
import ArtifactPreviewDialog from './components/ArtifactPreviewDialog.vue'
import TrajectoryCanvas from './components/TrajectoryCanvas.vue'
import ManualScoreForm from './components/ManualScoreForm.vue'
import ScoreOverrideDrawer from './components/ScoreOverrideDrawer.vue'
import LifecycleTimeline from './components/LifecycleTimeline.vue'

import type { TeacherAttemptFull, EvidenceEvent, ArtifactsTreeResponse } from '@/api/exam/attempts'
import {
  getAttemptFullApi,
  getAttemptEventsApi,
  getArtifactsTreeApi,
  getArtifactFileApi
} from '@/api/exam/attempts'

const route = useRoute()
const router = useRouter()

const attemptId = computed(() => Number(route.params.attempt_id))

// ─── 状态 ──────────────────────────────────────────────────
const loading = ref(true)
const loadError = ref<string | null>(null)
const attempt = ref<TeacherAttemptFull | null>(null)
const events = ref<EvidenceEvent[] | null>(null)
const artifactsTree = ref<ArtifactsTreeResponse | null>(null)
interface TrajectoryData {
  points: { t: number; x: number; y: number; theta?: number }[]
  start?: { x: number; y: number }
  goal?: { x: number; y: number }
  collisions?: { t: number; x: number; y: number }[]
}
const trajectoryData = ref<TrajectoryData | null>(null)
const trajectoryError = ref<string | null>(null)

const previewDialogVisible = ref(false)
const previewFilename = ref('')

// ─── 计算属性 ──────────────────────────────────────────────
const canSubmitScore = computed(
  () => attempt.value && ['completed', 'reviewed'].includes(attempt.value.status)
)

// ─── 生命周期 ──────────────────────────────────────────────
onMounted(loadAll)

async function loadAll() {
  loading.value = true
  loadError.value = null
  try {
    const [attemptRes, eventsRes, artifactsRes] = await Promise.all([
      getAttemptFullApi(attemptId.value),
      getAttemptEventsApi(attemptId.value),
      getArtifactsTreeApi(attemptId.value)
    ])
    attempt.value = attemptRes.data ?? null
    events.value = eventsRes.data?.items ?? []
    artifactsTree.value = artifactsRes.data ?? null

    // 若 artifacts 含 trajectory.json，自动加载
    const hasTrajectory = artifactsRes.data?.files.some((f) => f.name === 'trajectory.json')
    if (hasTrajectory) {
      await loadTrajectory()
    }
  } catch {
    loadError.value = '加载复核数据失败，请刷新重试'
  } finally {
    loading.value = false
  }
}

async function loadTrajectory() {
  trajectoryError.value = null
  try {
    const res = await getArtifactFileApi(attemptId.value, 'trajectory.json')
    const raw = res.data?.content
    if (!raw) return
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed.points)) {
      trajectoryError.value = '轨迹数据损坏（points 格式异常）'
      return
    }
    trajectoryData.value = parsed
  } catch {
    trajectoryError.value = '轨迹数据加载失败'
  }
}

// ─── 操作 ──────────────────────────────────────────────────
function openPreview(filename: string) {
  previewFilename.value = filename
  previewDialogVisible.value = true
}

async function openTrajectory(_filename: string) {
  // trajectory.json 直接展示已缓存数据，或重新加载
  if (!trajectoryData.value) await loadTrajectory()
  if (trajectoryError.value) ElMessage.warning(trajectoryError.value)
}

function handleScoreSubmitted(updated: TeacherAttemptFull) {
  attempt.value = updated
  ElMessage.success(`最终分：${updated.final_score?.toFixed(1) ?? '-'}`)
}

function handleOverridden(updated: TeacherAttemptFull) {
  attempt.value = updated
}

// ─── 辅助 ──────────────────────────────────────────────────
const STATUS_LABELS: Record<string, string> = {
  pending: '待开始',
  running: '进行中',
  scoring: '评分中',
  completed: '已完成',
  reviewed: '已复核',
  aborted: '已放弃',
  error: '异常'
}

function statusLabel(s: string): string {
  return STATUS_LABELS[s] ?? s
}

function statusTagType(s: string): 'success' | 'warning' | 'danger' | 'info' | 'primary' {
  if (s === 'completed' || s === 'reviewed') return 'success'
  if (s === 'running' || s === 'scoring') return 'warning'
  if (s === 'aborted' || s === 'error') return 'danger'
  return 'info'
}
</script>

<style scoped>
.exam-attempt-review {
  padding: 20px 24px;
  min-height: 100vh;
  background: var(--el-bg-color-page);
}

.review-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.title-main {
  font-size: 18px;
  font-weight: 600;
}

.title-sub {
  font-size: 14px;
  color: var(--el-text-color-secondary);
}

.ml-8 {
  margin-left: 8px;
}
.mt-16 {
  margin-top: 16px;
}

.page-loading,
.page-error {
  padding: 40px 0;
}

.review-section {
  margin-bottom: 16px;
}

.review-body {
  display: grid;
  grid-template-columns: 1fr 400px;
  gap: 16px;
  align-items: start;
}

.review-col-left,
.review-col-right {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.review-card {
  width: 100%;
}

.score-blocked {
  padding: 8px 0;
}
</style>
