<!--
  ==== 我的证书 ====
  解决的问题：学生参加校级比赛获奖后，系统自动生成电子证书，学生可在此查看、预览与下载，
    并记录是否已领取，作为获奖佐证材料。
  对应角色与路由：role=1 学生，路由 /my-certificates（隐藏在学生端「我的项目」分组）。
  依赖 API：
    - GET /api/certificates/my（getMyCertificates）分页拉取证书；
    - /api/files/preview/{attachment_id}、/api/files/download/{attachment_id} 查看与下载证书文件。
  业务规则：
    - 证书类型 cert_type：1=团队证书，2=个人证书；本页统一展示，不按类型过滤。
    - downloaded 由后端根据下载次数维护，下载后需延迟刷新才能显示「已领取」。
  关键交互流程：进入页面加载证书 -> 预览/下载通过 window.open 打开文件接口 ->
    下载后延时刷新列表更新领取状态。
-->
<template>
  <div class="my-certificates">
    <el-card shadow="never">
      <!-- 区块：卡片头部，展示证书总张数 -->
      <template #header>
        <div class="card-header">
          <span>我的证书</span>
          <span class="total">共 {{ total }} 张</span>
        </div>
      </template>

      <!-- 区块：空状态，提示证书由获奖自动生成，避免学生误以为需要手动申请 -->
      <el-empty v-if="!loading && rows.length === 0" description="暂无获奖证书，参加校级比赛获奖后自动生成" />

      <!-- 区块：证书表格，含竞赛、奖项、项目、编号、发证日期与领取状态 -->
      <el-table v-else v-loading="loading" :data="rows" border stripe>
        <!-- 序号列：跨页连续编号，按页码与行下标换算 -->
        <el-table-column label="序号" width="64" align="center">
          <template #default="{ $index }">{{ (page - 1) * pageSize + $index + 1 }}</template>
        </el-table-column>
        <el-table-column prop="competition_name" label="竞赛名称" min-width="180" show-overflow-tooltip />
        <!-- 奖项等级：用橙色标签突出，便于快速识别获奖层次 -->
        <el-table-column prop="award_level" label="奖项等级" width="120" align="center">
          <template #default="{ row }">
            <el-tag type="warning" effect="light">{{ row.award_level }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="project_name" label="项目名称" min-width="200" show-overflow-tooltip />
        <el-table-column prop="cert_no" label="证书编号" width="190" show-overflow-tooltip />
        <el-table-column prop="issue_date" label="发证日期" width="115" align="center" />
        <!-- 领取状态：已下载过显示绿色「已领取」，否则灰色「未领取」 -->
        <el-table-column label="领取状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.downloaded ? 'success' : 'info'" effect="light">
              {{ row.downloaded ? '已领取' : '未领取' }}
            </el-tag>
          </template>
        </el-table-column>
        <!-- 操作列：预览走浏览器内联展示，下载触发文件下载并累计领取次数 -->
        <el-table-column label="操作" width="150" align="center">
          <template #default="{ row }">
            <el-button link type="primary" @click="handlePreview(row)">预览</el-button>
            <el-button link type="primary" @click="handleDownload(row)">下载</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 区块：分页，切换页码或每页条数都会重新请求 -->
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
// ==================== 导入 ====================
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getMyCertificates, type CertificateItem } from '@/api/certificate'
import { useUserStore } from '@/store/user'

// ==================== 状态 ====================
/** 用户 Store：仅用于取 accessToken，给文件 URL 追加鉴权参数 */
const userStore = useUserStore()
/** 列表加载中标记，同时驱动表格遮罩与空状态判断 */
const loading = ref(false)
/** 当前页证书列表，元素为 CertificateItem */
const rows = ref<CertificateItem[]>([])
/** 证书总数，用于分页与头部统计 */
const total = ref(0)
/** 当前页码，从 1 开始 */
const page = ref(1)
/** 每页条数，默认 10，可切换 10/20/50 */
const pageSize = ref(10)

// ==================== 文件访问鉴权 ====================
/**
 * window.open 无法携带 Authorization 头，后端对文件接口开放 ?token= 兜底鉴权，
 * 因此把登录 token 拼到查询串上；无 token 时原样返回，让后端按未登录处理。
 * @param url 文件预览/下载地址
 * @returns 带 token 查询参数的完整地址
 */
function withToken(url: string): string {
  const token = userStore.accessToken
  if (!token) return url
  return `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}`
}

// ==================== 数据加载 ====================
/**
 * 分页拉取当前学生的证书。
 * 副作用：更新 rows / total 与 loading 状态；失败时弹出错误提示并保留旧数据。
 */
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

// ==================== 事件处理 ====================
/**
 * 每页条数变化：回到第一页重新请求，避免当前页码超出新的总页数。
 * 注：pageSize 已由 v-model:page-size 同步，这里只负责重置页码并加载。
 */
function handleSizeChange() {
  page.value = 1
  load()
}

/**
 * 预览证书：新标签页打开文件预览接口，noopener/noreferrer 防止被打开页反向控制本页。
 * @param row 证书行，使用 attachment_id 定位文件
 */
function handlePreview(row: CertificateItem) {
  window.open(withToken(`/api/files/preview/${row.attachment_id}`), '_blank', 'noopener,noreferrer')
}

/**
 * 下载证书：新标签页触发下载；后端会累加下载次数并更新领取状态，
 * 因此延时 800ms 再刷新列表，让「已领取」标签及时生效。
 * 副作用：打开下载地址、定时刷新列表。
 * @param row 证书行，使用 attachment_id 定位文件
 */
function handleDownload(row: CertificateItem) {
  window.open(withToken(`/api/files/download/${row.attachment_id}`), '_blank', 'noopener,noreferrer')
  // 下载计数由后端累加，刷新后展示最新领取状态
  setTimeout(load, 800)
}

// ==================== 生命周期 ====================
/** 页面挂载即加载第一页证书 */
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
