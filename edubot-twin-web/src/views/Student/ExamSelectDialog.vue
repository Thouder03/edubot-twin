<script setup lang="ts">
/**
 * ExamSelectDialog - 学生端考试选择弹窗
 *
 * 展示所有已发布可参加的考试，学生选择后跳转到仿真页考试模式
 */
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElButton, ElDialog, ElEmpty, ElTable, ElTableColumn, ElTag, ElMessage } from 'element-plus'
import { getPublishedExamsApi } from '@/api/exam/attempts'
import type { PublishedExamItem } from '@/api/exam/attempts'

const props = defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
}>()

const router = useRouter()

const loading = ref(false)
const exams = ref<PublishedExamItem[]>([])
const selectedExamId = ref<number | null>(null)

const MODE_LABEL: Record<string, string> = {
  result_run: '结果型',
  process_run: '过程型',
  multi_stage_run: '多阶段'
}
const MODE_TYPE: Record<string, 'primary' | 'success' | 'warning'> = {
  result_run: 'primary',
  process_run: 'success',
  multi_stage_run: 'warning'
}

function formatMinutes(ms: number): string {
  return Math.ceil(ms / 60000) + ' 分钟'
}

async function load() {
  loading.value = true
  try {
    const res = await getPublishedExamsApi()
    exams.value = res.data ?? []
    // 默认选中第一个
    if (exams.value.length > 0 && !selectedExamId.value) {
      selectedExamId.value = exams.value[0].exam_id
    }
  } catch {
    ElMessage.error('获取考试列表失败')
    exams.value = []
  } finally {
    loading.value = false
  }
}

function handleRowClick(row: PublishedExamItem) {
  selectedExamId.value = row.exam_id
}

function handleRowDblClick(row: PublishedExamItem) {
  selectedExamId.value = row.exam_id
  handleConfirm()
}

function handleConfirm() {
  if (!selectedExamId.value) {
    ElMessage.warning('请先选择一个考试')
    return
  }
  emit('update:visible', false)

  const url = router.resolve({
    name: 'Simulation',
    query: { exam_id: String(selectedExamId.value) }
  }).href

  const newWin = window.open(url, '_blank')
  if (!newWin) {
    ElMessage.warning('新标签页被拦截，将在当前标签页跳转')
    router.push({ name: 'Simulation', query: { exam_id: String(selectedExamId.value) } })
  }
}

watch(
  () => props.visible,
  (v) => {
    if (v) {
      selectedExamId.value = null
      load()
    }
  }
)
</script>

<template>
  <ElDialog
    :model-value="props.visible"
    title="选择考试"
    width="640px"
    :close-on-click-modal="false"
    @update:model-value="emit('update:visible', $event)"
  >
    <div v-loading="loading" class="exam-select-body">
      <div v-if="!loading && exams.length === 0" class="empty-wrap">
        <ElEmpty description="暂无已发布的考试" :image-size="80" />
      </div>

      <template v-else>
        <ElTable
          :data="exams"
          size="small"
          highlight-current-row
          :current-row-key="selectedExamId ?? undefined"
          row-key="exam_id"
          style="width: 100%"
          @row-click="handleRowClick"
          @row-dblclick="handleRowDblClick"
        >
          <ElTableColumn label="考试名称" min-width="160">
            <template #default="{ row }">
              <div class="exam-name">{{ row.name }}</div>
              <div v-if="row.description" class="exam-desc">{{ row.description }}</div>
            </template>
          </ElTableColumn>
          <ElTableColumn label="模式" width="80">
            <template #default="{ row }">
              <ElTag :type="MODE_TYPE[row.exam_mode] ?? 'info'" size="small">
                {{ MODE_LABEL[row.exam_mode] ?? row.exam_mode }}
              </ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn label="时限" width="80">
            <template #default="{ row }">{{ formatMinutes(row.time_limit_ms) }}</template>
          </ElTableColumn>
          <ElTableColumn label="最多尝试" width="80">
            <template #default="{ row }">{{ row.max_attempts }} 次</template>
          </ElTableColumn>
        </ElTable>
        <div class="hint">双击行或选中后点击「进入考试」</div>
      </template>
    </div>

    <template #footer>
      <ElButton @click="emit('update:visible', false)">取消</ElButton>
      <ElButton type="primary" :disabled="!selectedExamId" @click="handleConfirm">
        进入考试
      </ElButton>
    </template>
  </ElDialog>
</template>

<style lang="less" scoped>
.exam-select-body {
  min-height: 200px;

  .empty-wrap {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 160px;
  }

  .exam-name {
    font-size: 14px;
    font-weight: 500;
    color: #303133;
  }

  .exam-desc {
    font-size: 12px;
    color: #909399;
    margin-top: 2px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 220px;
  }

  .hint {
    font-size: 12px;
    color: #c0c4cc;
    text-align: center;
    margin-top: 10px;
  }
}

:deep(.el-table__row) {
  cursor: pointer;
}

:deep(.el-table__row.current-row) {
  background-color: var(--el-color-primary-light-9) !important;
}
</style>
