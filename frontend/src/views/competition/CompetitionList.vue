<!--
  ==== 创新创业大赛（浏览端） ====

  页面职责：以卡片网格展示学校发布的赛事，支持关键词/类型/级别筛选、分页浏览、
            点击卡片查看详情，并可跳转赛事官方链接。
  角色与路由：roles [1,2,3,4] 均可访问，路由 /competitions（name: CompetitionList）。
            学生、教师、专家主要在此浏览赛事并判断是否可申报。
  调用接口：GET /api/competitions        分页列表（page / page_size，返回 items + total）
            GET /api/competitions/:id    详情（后端同时累加浏览次数）
  关键交互：点击卡片打开右侧详情抽屉；详情返回后把 view_count 回写列表对应项，
            使卡片浏览数无需刷新即可更新；封面缺省时按比赛类型从默认海报池取图；
            列表仅展示报名中(1)、进行中(2)，已结束(3)/已取消(4) 由后端按下架处理。
-->
<template>
  <div class="page-container">
    <!-- 区块：页面标题与说明 -->
    <el-card shadow="never" class="header-card">
      <div class="header">
        <div class="title-area">
          <el-icon :size="24" color="#409EFF"><Trophy /></el-icon>
          <h2>创新创业大赛</h2>
        </div>
        <p class="subtitle">浏览学校发布的各类创新创业赛事，积极报名参与</p>
      </div>
    </el-card>

    <!-- 区块：筛选区（关键词 / 比赛类型 / 级别；回车即可查询） -->
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

    <!-- 区块：赛事卡片网格（整卡可点击进入详情，无数据时显示空状态） -->
    <div class="competition-grid" v-loading="loading">
      <div v-for="item in list" :key="item.id" class="competition-card" @click="goDetail(item.id)">
        <!-- 封面区：左上状态角标（0 草稿 / 1 报名中 / 2 进行中 / 3 已结束 / 4 已取消），右上级别角标（1 校级 / 2 省级 / 3 国家级） -->
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

    <!-- 区块：分页区（每页 9 条，与三列卡片布局一一对应） -->
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

    <!-- 区块：详情抽屉（基础信息、简介/要求/奖项，及官方链接入口） -->
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
// ==================== 导入区 ====================
import { ref, onMounted } from 'vue'
import { Trophy, Search, Refresh, OfficeBuilding, Location, View, Link } from '@element-plus/icons-vue'
import { getCompetitionList, getCompetitionDetail, type CompetitionListItem, type CompetitionDetail } from '@/api/competition'

// ==================== 枚举与展示映射 ====================
// 比赛类型 competition_type：1 创新训练类 / 2 创业实践类 / 3 学科竞赛类 / 4 综合类
const typeMap: Record<number, string> = { 1: '创新训练类', 2: '创业实践类', 3: '学科竞赛类', 4: '综合类' }
// 比赛级别 level：1 校级 / 2 省级 / 3 国家级
const levelMap: Record<number, string> = { 1: '校级', 2: '省级', 3: '国家级' }

// ==================== 响应式状态 ====================
// 卡片列表加载态：控制网格区域 v-loading
const loading = ref(false)
// 当前页比赛数据，对应 GET /api/competitions 返回的 items
const list = ref<CompetitionListItem[]>([])
// 列表总数，对应接口返回的 total，用于分页组件
const total = ref(0)
// 当前查看的比赛详情，对应 GET /api/competitions/:id
const detail = ref<CompetitionDetail | null>(null)
// 详情抽屉显隐
const detailVisible = ref(false)

// ==================== 查询条件与分页 ====================
// 列表查询参数，作为 GET /api/competitions 的 query；page_size=9 与三列卡片布局匹配
const searchForm = ref({ page: 1, page_size: 9, keyword: '', competition_type: undefined as number | undefined, level: undefined as number | undefined })

// 默认封面图池（大赛宣传海报），按比赛类型分配：
// key 为 competition_type（1 创新训练 / 2 创业实践 / 3 学科竞赛 / 4 综合），value 为候选海报路径
const defaultCovers: Record<number, string[]> = {
  1: ['/images/competitions/poster_innovation_experience.jpg', '/images/competitions/poster_school_training.jpg'],
  2: ['/images/competitions/poster_cxcyds.jpg', '/images/competitions/poster_chuangqingchun.jpg', '/images/competitions/poster_ec_san_chuang.jpg'],
  3: ['/images/competitions/poster_math_modeling.jpg'],
  4: ['/images/competitions/poster_internet_plus.jpg', '/images/competitions/poster_tiaozhanbei.jpg', '/images/competitions/poster_ican.jpg'],
}

/**
 * 计算卡片/详情封面地址。
 * @param item 比赛数据（需要 cover_image / competition_type / id）
 * @returns 有封面图时直接使用，否则按类型从海报池中按 id 取模选择一张，保证视觉不空
 */
function coverUrl(item: any): string {
  if (item.cover_image) {
    return item.cover_image
  }
  // 无封面图时，按比赛类型分配真实默认图片
  const pool = defaultCovers[item.competition_type] || defaultCovers[1]
  return pool[item.id % pool.length]
}

/** 状态码转 el-tag 颜色：草稿灰、报名中绿、进行中橙、已结束默认色、已取消红 */
function statusTagType(status: number) {
  return ({ 0: 'info', 1: 'success', 2: 'warning', 3: '', 4: 'danger' } as Record<number, string>)[status] || 'info'
}

/** 把日期时间截成 yyyy-MM-dd 展示；空值显示 '-' @param d 后端日期字符串 */
function formatDate(d: string | null) {
  if (!d) return '-'
  return d.substring(0, 10)
}

// ==================== 数据加载与筛选 ====================
/**
 * 加载当前页比赛列表。
 * 副作用：写入 loading、list、total；兼容 ApiResponse 与直接返回 data 两种结构。
 */
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

/** 点击查询：回到第 1 页后重新请求，避免筛选后页码越界 */
function handleSearch() { searchForm.value.page = 1; loadData() }
/** 重置全部筛选条件并回到第 1 页重新加载 */
function handleReset() {
  searchForm.value = { page: 1, page_size: 9, keyword: '', competition_type: undefined, level: undefined }
  loadData()
}

// ==================== 详情交互 ====================
/**
 * 打开比赛详情抽屉。
 * @param id 比赛 ID
 * 副作用：GET 详情、把最新 view_count 回写到列表对应卡片、打开抽屉。
 */
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

/** 在新标签页打开赛事官方链接，避免当前浏览列表被覆盖 @param url 官方地址 */
function openOfficial(url: string) { window.open(url, '_blank') }

// ==================== 生命周期 ====================
// 首次进入按默认条件加载第一页；离开页面后筛选状态不保留
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
