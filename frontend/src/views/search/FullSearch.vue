<!--
  全文检索页
  关键词检索项目名称、简介、成果、团队成员，结果关键词高亮
  F21 新增：搜索联想/历史/热门建议、热门词胶囊
-->
<template>
  <div class="page-container">
    <el-card shadow="never">
      <div class="search-box">
        <el-autocomplete
          v-model="keyword"
          :fetch-suggestions="querySearch"
          placeholder="搜索项目名称、简介、成果、团队成员..."
          size="large"
          :prefix-icon="Search"
          @keyup.enter="handleSearch"
          @select="handleSelectSuggestion"
          clearable
          class="search-autocomplete"
          popper-class="search-suggestion-popper"
          ref="autocompleteRef"
        >
          <template #default="{ item }">
            <div class="suggestion-item">
              <span class="suggestion-icon">{{ item.icon }}</span>
              <span class="suggestion-text" v-html="highlightMatch(item.value)"></span>
            </div>
          </template>

          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
          <template #append>
            <el-button type="primary" @click="handleSearch">搜索</el-button>
          </template>

          <template #footer>
            <div class="suggestion-footer">
              <el-button
                v-if="history.length > 0"
                link
                type="danger"
                size="small"
                @click="handleClearHistory"
              >
                🗑️ 清除历史
              </el-button>
              <span class="footer-tip" v-else>暂无搜索历史</span>
            </div>
          </template>
        </el-autocomplete>
      </div>

      <div v-if="searched" class="search-results">
        <div class="hot-tags-row" v-if="!searched || results.length >= 0">
          <span class="hot-label">🔥 大家都在搜：</span>
          <el-tag
            v-for="hk in hotKeywords.slice(0, 6)"
            :key="hk"
            class="hot-tag"
            effect="plain"
            round
            @click="handleHotClick(hk)"
          >
            {{ hk }}
          </el-tag>
        </div>

        <el-alert v-if="filterSummary" type="info" :closable="false" show-icon class="result-summary-alert">
          {{ filterSummary }}
        </el-alert>

        <p class="result-summary">共找到 {{ total }} 条结果</p>
        <el-card
          v-for="item in results"
          :key="item.id"
          shadow="hover"
          class="result-item"
          @click="projectDetailStore.open(item.project_id)"
        >
          <h3 v-html="highlight(item.project_name)"></h3>
          <p class="result-abstract" v-html="highlight(item.project_summary || '')"></p>
          <div class="result-meta">
            <span class="meta-item">负责人：{{ item.leader_name }}</span>
            <span class="meta-item">学院：{{ item.college_name }}</span>
          </div>
        </el-card>
        <EmptyIllustration v-if="results.length === 0" type="search" description="未找到匹配结果" />
      </div>
      <EmptyIllustration v-else type="search" description="输入关键词搜索项目" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Search } from '@element-plus/icons-vue'
import EmptyIllustration from '@/components/EmptyIllustration.vue'
import { fullTextSearch } from '@/api/common'
import { useSearchSuggestions } from '@/composables/useSearchSuggestions'
import { useDebounce } from '@/composables/useDebounce'
import { useProjectDetailStore } from '@/store/projectDetail'

const router = useRouter()
const projectDetailStore = useProjectDetailStore()
const keyword = ref('')
const results = ref<any[]>([])
const total = ref(0)
const searched = ref(false)
const autocompleteRef = ref()

const { history, suggestions, hotKeywords, addHistory, clearHistory } = useSearchSuggestions()

const filterSummary = computed(() => {
  if (!searched.value) return ''
  const kw = keyword.value.trim()
  if (!kw) return ''
  return `已筛选关键词：「${kw}」，共 ${total.value} 项结果`
})

function querySearch(queryString: string, cb: (arr: any[]) => void) {
  const list = suggestions(queryString)
  cb(list)
}

function handleSelectSuggestion(item: any) {
  keyword.value = item.value
  handleSearch()
}

function handleHotClick(kw: string) {
  keyword.value = kw
  handleSearch()
}

function handleClearHistory() {
  clearHistory()
  autocompleteRef.value?.focus?.()
}

async function doSearch() {
  const kw = keyword.value.trim()
  if (!kw) return
  addHistory(kw)
  searched.value = true
  autocompleteRef.value?.blur?.()
  try {
    const res = await fullTextSearch({ keyword: kw, page: 1, page_size: 20 })
    results.value = res.data.items || res.data || []
    total.value = res.data.total || results.value.length
  } catch {
    results.value = []
    total.value = 0
  }
}

const debouncedSearch = useDebounce(doSearch, 400)

watch(keyword, () => {
  if (keyword.value.trim()) {
    debouncedSearch()
  }
})

function handleSearch() {
  debouncedSearch.flush()
}

function highlight(text: string): string {
  if (!keyword.value || !text) return text
  try {
    const reg = new RegExp(`(${keyword.value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi')
    return String(text).replace(reg, '<mark style="background: #fff3cd; padding: 0 2px;">$1</mark>')
  } catch {
    return text
  }
}

function highlightMatch(text: string): string {
  const kw = keyword.value.trim()
  if (!kw || !text) return text
  try {
    const reg = new RegExp(`(${kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi')
    return String(text).replace(reg, '<span style="color: #409EFF; font-weight: 600;">$1</span>')
  } catch {
    return text
  }
}
</script>

<style scoped>
.search-box {
  margin-bottom: 20px;
}

.search-autocomplete {
  width: 100%;
}

.hot-tags-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.hot-label {
  font-size: 13px;
  color: #909399;
  flex-shrink: 0;
}

.hot-tag {
  cursor: pointer;
  transition: all 0.2s;
}

.hot-tag:hover {
  background-color: #ecf5ff;
  border-color: #409EFF;
  color: #409EFF;
}

.result-summary-alert {
  margin-bottom: 12px;
}

.result-summary {
  color: #909399;
  font-size: 14px;
  margin-bottom: 12px;
}

.result-item {
  margin-bottom: 12px;
  cursor: pointer;
}

.result-item h3 {
  font-size: 16px;
  color: #409EFF;
  margin-bottom: 8px;
}

.result-abstract {
  font-size: 14px;
  color: #606266;
  margin-bottom: 8px;
  line-height: 1.6;
}

.result-meta {
  display: flex;
  gap: 16px;
  align-items: center;
  font-size: 13px;
  color: #909399;
}

.meta-item {
  font-size: 13px;
}

:deep(.suggestion-item) {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}

:deep(.suggestion-icon) {
  font-size: 14px;
  width: 20px;
  text-align: center;
}

:deep(.suggestion-text) {
  flex: 1;
  font-size: 14px;
}

:deep(.suggestion-footer) {
  padding: 8px 12px;
  border-top: 1px solid #ebeef5;
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 36px;
}

:deep(.footer-tip) {
  font-size: 12px;
  color: #c0c4cc;
}
</style>
