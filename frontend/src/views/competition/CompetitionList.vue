<!--
  创新创业大赛 - 学生端列表页
  所有登录用户可查看已发布的比赛
-->
<template>
  <div class="page-container">
    <el-card shadow="never" class="header-card">
      <div class="header">
        <div class="title-area">
          <el-icon :size="24" color="#409EFF"><Trophy /></el-icon>
          <h2>创新创业大赛</h2>
        </div>
        <p class="subtitle">浏览学校发布的各类创新创业赛事，积极报名参与</p>
      </div>
    </el-card>

    <el-card shadow="never" class="filter-card">
      <el-form :inline="true" :model="searchForm">
        <el-form-item label="关键词">
          <el-input v-model="searchForm.keyword" placeholder="比赛名称/主办方" clearable style="width:200px" @keyup.enter="handleSearch" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="searchForm.competition_type" placeholder="全部" clearable style="width:140px">
            <el-option v-for="(label, val) in typeMap" :key="val" :label="label" :value="Number(val)" />
          </el-select>
        </el-form-item>
        <el-form-item label="级别">
          <el-select v-model="searchForm.level" placeholder="全部" clearable style="width:120px">
            <el-option v-for="(label, val) in levelMap" :key="val" :label="label" :value="Number(val)" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
          <el-button :icon="Refresh" @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <div class="competition-grid" v-loading="loading">
      <div v-for="item in list" :key="item.id" class="competition-card" @click="goDetail(item.id)">
        <div class="card-cover">
          <img :src="coverUrl(item)" class="cover-img" alt="" />
          <el-tag :type="statusTagType(item.status)" effect="dark" class="status-tag">{{ item.status_name }}</el-tag>
          <span class="level-badge" :class="`level-${item.level}`">{{ item.level_name }}</span>
        </div>
        <div class="card-body">
          <h3 class="card-title">
            {{ item.title }}
            <span v-if="item.session" class="session-badge">{{ item.session }}</span>
          </h3>
          <div class="card-meta">
            <span v-if="item.organizer"><el-icon><OfficeBuilding /></el-icon> {{ item.organizer }}</span>
            <span v-if="item.location"><el-icon><Location /></el-icon> {{ item.location }}</span>
          </div>
          <div class="card-dates">
            <div class="date-row">
              <span class="date-label">报名</span>
              <span>{{ formatDate(item.registration_start) }} ~ {{ formatDate(item.registration_end) }}</span>
            </div>
            <div class="date-row">
              <span class="date-label">比赛</span>
              <span>{{ formatDate(item.competition_start) }} ~ {{ formatDate(item.competition_end) }}</span>
            </div>
          </div>
          <div class="card-footer">
            <el-tag size="small" type="info">{{ item.competition_type_name }}</el-tag>
            <span class="view-count"><el-icon><View /></el-icon> {{ item.view_count }}</span>
          </div>
        </div>
      </div>
      <el-empty v-if="!loading && list.length === 0" description="暂无比赛" />
    </div>

    <div class="pagination-wrap" v-if="total > 0">
      <el-pagination
        v-model:current-page="searchForm.page"
        v-model:page-size="searchForm.page_size"
        :page-sizes="[9, 18, 36]"
        :total="total"
        layout="total, prev, pager, next"
        @size-change="loadData"
        @current-change="loadData"
      />
    </div>

    <!-- 详情抽屉 -->
    <el-drawer v-model="detailVisible" :title="detail?.title || '比赛详情'" size="50%" direction="rtl">
      <div v-if="detail" class="detail-content">
        <div class="detail-cover">
          <img :src="coverUrl(detail)" class="detail-cover-img" alt="" />
        </div>
        <div class="detail-meta">
          <el-tag :type="statusTagType(detail.status)" effect="dark">{{ detail.status_name }}</el-tag>
          <el-tag type="warning">{{ detail.level_name }}</el-tag>
          <el-tag type="info">{{ detail.competition_type_name }}</el-tag>
        </div>
        <el-descriptions :column="2" border class="detail-desc">
          <el-descriptions-item label="届次">{{ detail.session || '-' }}</el-descriptions-item>
          <el-descriptions-item label="主办方">{{ detail.organizer || '-' }}</el-descriptions-item>
          <el-descriptions-item label="承办方">{{ detail.co_organizer || '-' }}</el-descriptions-item>
          <el-descriptions-item label="报名时间">{{ formatDate(detail.registration_start) }} ~ {{ formatDate(detail.registration_end) }}</el-descriptions-item>
          <el-descriptions-item label="比赛时间">{{ formatDate(detail.competition_start) }} ~ {{ formatDate(detail.competition_end) }}</el-descriptions-item>
          <el-descriptions-item label="比赛地点">{{ detail.location || '-' }}</el-descriptions-item>
          <el-descriptions-item label="联系方式">{{ detail.contact || '-' }}</el-descriptions-item>
        </el-descriptions>
        <div v-if="detail.description" class="detail-section">
          <h4>比赛简介</h4>
          <p>{{ detail.description }}</p>
        </div>
        <div v-if="detail.requirements" class="detail-section">
          <h4>参赛要求</h4>
          <p>{{ detail.requirements }}</p>
        </div>
        <div v-if="detail.rewards" class="detail-section">
          <h4>奖项设置</h4>
          <p>{{ detail.rewards }}</p>
        </div>
        <div v-if="detail.official_url" class="detail-section">
          <el-button type="primary" :icon="Link" @click="openOfficial(detail.official_url)">查看官方详情</el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Trophy, Search, Refresh, OfficeBuilding, Location, View, Link } from '@element-plus/icons-vue'
import { getCompetitionList, getCompetitionDetail, type CompetitionListItem, type CompetitionDetail } from '@/api/competition'

const typeMap: Record<number, string> = { 1: '创新训练类', 2: '创业实践类', 3: '学科竞赛类', 4: '综合类' }
const levelMap: Record<number, string> = { 1: '校级', 2: '省级', 3: '国家级' }

const loading = ref(false)
const list = ref<CompetitionListItem[]>([])
const total = ref(0)
const detail = ref<CompetitionDetail | null>(null)
const detailVisible = ref(false)

const searchForm = ref({ page: 1, page_size: 9, keyword: '', competition_type: undefined as number | undefined, level: undefined as number | undefined })

// 默认封面图池（大赛宣传海报），按比赛类型分配
const defaultCovers: Record<number, string[]> = {
  1: ['/images/competitions/poster_innovation_experience.jpg', '/images/competitions/poster_school_training.jpg'],
  2: ['/images/competitions/poster_cxcyds.jpg', '/images/competitions/poster_chuangqingchun.jpg', '/images/competitions/poster_ec_san_chuang.jpg'],
  3: ['/images/competitions/poster_math_modeling.jpg'],
  4: ['/images/competitions/poster_internet_plus.jpg', '/images/competitions/poster_tiaozhanbei.jpg', '/images/competitions/poster_ican.jpg'],
}

function coverUrl(item: any): string {
  if (item.cover_image) {
    return item.cover_image
  }
  // 无封面图时，按比赛类型分配真实默认图片
  const pool = defaultCovers[item.competition_type] || defaultCovers[1]
  return pool[item.id % pool.length]
}

function statusTagType(status: number) {
  return ({ 0: 'info', 1: 'success', 2: 'warning', 3: '', 4: 'danger' } as Record<number, string>)[status] || 'info'
}

function formatDate(d: string | null) {
  if (!d) return '-'
  return d.substring(0, 10)
}

async function loadData() {
  loading.value = true
  try {
    const res = await getCompetitionList(searchForm.value)
    // 兼容返回 ApiResponse（{code,message,data}）或直接返回 data 两种情况
    const data = (res as any).data ?? res
    list.value = data.items || []
    total.value = data.total || 0
  } finally {
    loading.value = false
  }
}

function handleSearch() { searchForm.value.page = 1; loadData() }
function handleReset() {
  searchForm.value = { page: 1, page_size: 9, keyword: '', competition_type: undefined, level: undefined }
  loadData()
}

async function goDetail(id: number) {
  const res = await getCompetitionDetail(id)
  detail.value = (res as any).data ?? res
  // 更新列表中对应项的浏览次数
  const idx = list.value.findIndex(item => item.id === id)
  if (idx !== -1 && detail.value) {
    list.value[idx].view_count = detail.value.view_count
  }
  detailVisible.value = true
}

function openOfficial(url: string) { window.open(url, '_blank') }

onMounted(loadData)
</script>

<style scoped>
.page-container { padding: 16px; }
.header-card { margin-bottom: 12px; }
.header { display: flex; flex-direction: column; gap: 6px; }
.title-area { display: flex; align-items: center; gap: 10px; }
.title-area h2 { margin: 0; font-size: 20px; }
.subtitle { margin: 0; color: #909399; font-size: 13px; }
.filter-card { margin-bottom: 16px; }

.competition-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}
.competition-card {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
  background: #fff;
}
.competition-card:hover { transform: translateY(-4px); box-shadow: 0 8px 24px rgba(0,0,0,0.12); }
.card-cover {
  position: relative;
  overflow: hidden;
  line-height: 0;
}
.cover-img {
  width: 100%;
  height: auto;
  display: block;
}
.status-tag { position: absolute; top: 10px; left: 10px; }
.level-badge {
  position: absolute; top: 10px; right: 10px;
  padding: 3px 10px; border-radius: 10px;
  font-size: 12px; font-weight: 600; color: #fff;
  line-height: 1.4;
}
.level-1 { background: #909399; }  /* 校级 灰色 */
.level-2 { background: #409eff; }  /* 省级 蓝色 */
.level-3 { background: #f56c6c; }  /* 国家级 红色 */
.card-body { padding: 14px; }
.card-title { margin: 0 0 8px; font-size: 16px; color: #303133; }
.session-badge {
  display: inline-block; margin-left: 6px; padding: 1px 6px;
  font-size: 12px; font-weight: normal; color: #409eff;
  background: #ecf5ff; border: 1px solid #b3d8ff; border-radius: 4px;
}
.card-meta { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: #606266; margin-bottom: 10px; }
.card-meta span { display: flex; align-items: center; gap: 4px; }
.card-dates { font-size: 12px; color: #909399; line-height: 1.8; margin-bottom: 10px; }
.date-label { display: inline-block; width: 36px; color: #c0c4cc; }
.card-footer { display: flex; justify-content: space-between; align-items: center; }
.view-count { font-size: 12px; color: #909399; display: flex; align-items: center; gap: 3px; }

.pagination-wrap { margin-top: 20px; display: flex; justify-content: center; }

.detail-cover {
  border-radius: 8px;
  margin-bottom: 16px;
  overflow: hidden;
  line-height: 0;
}
.detail-cover-img {
  width: 100%;
  height: auto;
  display: block;
  border-radius: 8px;
}
.detail-meta { display: flex; gap: 8px; margin-bottom: 16px; }
.detail-section { margin-top: 18px; }
.detail-section h4 { margin: 0 0 8px; font-size: 15px; color: #303133; }
.detail-section p { margin: 0; color: #606266; line-height: 1.7; white-space: pre-wrap; }
</style>
