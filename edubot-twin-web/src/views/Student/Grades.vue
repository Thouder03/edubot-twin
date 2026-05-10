<script setup lang="ts">
/**
 * Grades - 学生端成绩预览列表页（第16期）
 *
 * 路由：/student/grades
 * 功能：展示当前学生所有已完成考试的最高分摘要，点击行跳转成绩详情页
 *       展开行显示「指标」，与教师端成绩预览保持一致的展示风格
 */
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElTable, ElTableColumn, ElTag, ElTooltip, ElEmpty } from 'element-plus'
import { ContentWrap } from '@/components/ContentWrap'
import { getMyGradeSummaryApi, type StudentGradeSummaryItem } from '@/api/student/grades'
import MetricsKvTable from '@/components/Grade/MetricsKvTable.vue'

const router = useRouter()

const loading = ref(false)
const items = ref<StudentGradeSummaryItem[]>([])

async function load() {
  loading.value = true
  try {
    const res = await getMyGradeSummaryApi()
    items.value = res.data ?? []
  } finally {
    loading.value = false
  }
}

// 点击行跳转详情，但跳过展开列的点击
function onRowClick(row: StudentGradeSummaryItem, column: { type?: string }) {
  if (column.type === 'expand') return
  router.push(`/student/grades/${row.exam_id}`)
}

function formatDate(iso: string | null): string {
  if (!iso) return '-'
  return new Date(iso).toLocaleDateString('zh-CN')
}

function truncate(text: string | null, len = 100): string {
  if (!text) return '-'
  return text.length > len ? text.slice(0, len) + '…' : text
}

const STATUS_LABEL: Record<string, string> = {
  completed: '已完成',
  reviewed: '已复核'
}

onMounted(load)
</script>

<template>
  <ContentWrap title="我的成绩">
    <div v-loading="loading">
      <ElEmpty
        v-if="!loading && items.length === 0"
        description="暂无成绩，完成考试后在此查看"
        class="py-12"
      />

      <ElTable
        v-else
        :data="items"
        border
        row-key="exam_id"
        row-class-name="cursor-pointer"
        @row-click="onRowClick"
      >
        <!-- 展开列：三区（评测详情 | 指标 | 自定义字段） -->
        <ElTableColumn type="expand">
          <template #default="{ row }">
            <div class="grade-expand px-4 py-3 bg-#f8f9fa rounded">
              <div class="flex gap-6">
                <!-- 评测详情 -->
                <div class="flex-1">
                  <div class="section-title">📊 评测详情</div>
                  <table class="kv-table">
                    <tbody>
                      <tr>
                        <td class="kv-key">评测评语</td>
                        <td class="kv-val">{{ row.summary || '-' }}</td>
                      </tr>
                      <tr>
                        <td class="kv-key">教师评语</td>
                        <td class="kv-val">{{ row.teacher_comment || '-' }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <!-- 指标 -->
                <div class="flex-1">
                  <div class="section-title">📈 指标</div>
                  <MetricsKvTable :metrics="row.metrics" />
                </div>
                <!-- 自定义字段 -->
                <div class="flex-1">
                  <div class="section-title">📋 自定义字段</div>
                  <MetricsKvTable :metrics="row.custom_fields" />
                </div>
              </div>
            </div>
          </template>
        </ElTableColumn>

        <ElTableColumn label="考试名称" prop="exam_name" min-width="160" show-overflow-tooltip />
        <ElTableColumn label="最高分" width="90" align="right">
          <template #default="{ row }">
            {{ row.objective_score ?? '-' }}
          </template>
        </ElTableColumn>
        <ElTableColumn label="教师评分" width="90" align="right">
          <template #default="{ row }">
            {{ row.manual_score ?? '-' }}
          </template>
        </ElTableColumn>
        <ElTableColumn label="最终分" width="90" align="right">
          <template #default="{ row }">
            {{ row.final_score ?? '-' }}
          </template>
        </ElTableColumn>
        <ElTableColumn label="Pass" width="70" align="center">
          <template #default="{ row }">
            <span v-if="row.pass === true">✅</span>
            <span v-else-if="row.pass === false">❌</span>
            <span v-else>-</span>
          </template>
        </ElTableColumn>
        <ElTableColumn label="评测评语" min-width="180">
          <template #default="{ row }">
            <ElTooltip
              v-if="row.summary && row.summary.length > 100"
              :content="row.summary"
              placement="top"
              :show-after="300"
            >
              <span class="text-#606266 cursor-pointer">{{ truncate(row.summary) }}</span>
            </ElTooltip>
            <span v-else class="text-#606266">{{ row.summary || '-' }}</span>
            <!-- 教师评语标记 -->
            <ElTooltip v-if="row.teacher_comment" content="教师有评语，点击查看" placement="top">
              <span class="ml-1 text-#409eff cursor-pointer">📝</span>
            </ElTooltip>
          </template>
        </ElTableColumn>
        <ElTableColumn label="状态" width="90" align="center">
          <template #default="{ row }">
            <ElTag type="success" size="small">
              {{ STATUS_LABEL[row.status] ?? row.status }}
            </ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="完成时间" width="110" align="center">
          <template #default="{ row }">{{ formatDate(row.ended_at) }}</template>
        </ElTableColumn>
      </ElTable>

      <div v-if="items.length > 0" class="text-center text-13px text-#909399 mt-3">
        点击任意行查看该考试的所有尝试详情；点击展开图标查看指标数据
      </div>
    </div>
  </ContentWrap>
</template>

<style scoped>
:deep(.cursor-pointer) {
  cursor: pointer;
}
:deep(.cursor-pointer:hover td) {
  background: #f5f7fa !important;
}
.grade-expand {
  border-radius: 4px;
}
.section-title {
  font-size: 12px;
  font-weight: 600;
  color: #606266;
  margin-bottom: 6px;
}
.kv-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.kv-table tr:hover {
  background: #f0f2f5;
}
.kv-key {
  color: #606266;
  padding: 3px 12px 3px 0;
  white-space: nowrap;
  width: 40%;
}
.kv-val {
  color: #303133;
  padding: 3px 0;
  word-break: break-all;
}
</style>
