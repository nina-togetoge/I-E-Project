<template>
  <div class="my-certificates">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>我的证书</span>
          <span class="total">共 {{ total }} 张</span>
        </div>
      </template>

      <el-empty v-if="!loading && rows.length === 0" description="暂无获奖证书，参加校级比赛获奖后自动生成" />

      <el-table v-else v-loading="loading" :data="rows" border stripe>
        <el-table-column label="序号" width="64" align="center">
          <template #default="{ $index }">{{ (page - 1) * pageSize + $index + 1 }}</template>
        </el-table-column>
        <el-table-column prop="competition_name" label="竞赛名称" min-width="180" show-overflow-tooltip />
        <el-table-column prop="award_level" label="奖项等级" width="120" align="center">
          <template #default="{ row }">
            <el-tag type="warning" effect="light">{{ row.award_level }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="project_name" label="项目名称" min-width="200" show-overflow-tooltip />
        <el-table-column prop="cert_no" label="证书编号" width="190" show-overflow-tooltip />
        <el-table-column prop="issue_date" label="发证日期" width="115" align="center" />
        <el-table-column label="领取状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.downloaded ? 'success' : 'info'" effect="light">
              {{ row.downloaded ? '已领取' : '未领取' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" align="center">
          <template #default="{ row }">
            <el-button link type="primary" @click="handlePreview(row)">预览</el-button>
            <el-button link type="primary" @click="handleDownload(row)">下载</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          background
          @current-change="load"
          @size-change="handleSizeChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getMyCertificates, type CertificateItem } from '@/api/certificate'
import { useUserStore } from '@/store/user'

const userStore = useUserStore()
const loading = ref(false)
const rows = ref<CertificateItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)

/** window.open 无法携带 Authorization 头，后端对文件接口开放 ?token= 兜底鉴权 */
function withToken(url: string): string {
  const token = userStore.accessToken
  if (!token) return url
  return `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}`
}

async function load() {
  loading.value = true
  try {
    const res: any = await getMyCertificates({ page: page.value, page_size: pageSize.value })
    rows.value = res.data?.items || []
    total.value = res.data?.total || 0
  } catch (e: any) {
    ElMessage.error(e?.message || '证书加载失败')
  } finally {
    loading.value = false
  }
}

function handleSizeChange() {
  page.value = 1
  load()
}

function handlePreview(row: CertificateItem) {
  window.open(withToken(`/api/files/preview/${row.attachment_id}`), '_blank', 'noopener,noreferrer')
}

function handleDownload(row: CertificateItem) {
  window.open(withToken(`/api/files/download/${row.attachment_id}`), '_blank', 'noopener,noreferrer')
  // 下载计数由后端累加，刷新后展示最新领取状态
  setTimeout(load, 800)
}

onMounted(load)
</script>

<style scoped>
.my-certificates {
  padding: 16px;
}
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.total {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}
</style>
