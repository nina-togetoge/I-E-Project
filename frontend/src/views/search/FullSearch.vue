<!--
  全文检索页
  关键词检索项目名称、简介、成果、团队成员，结果关键词高亮
-->
<template>
  <div class="page-container">
    <el-card shadow="never">
      <div class="search-box">
        <el-input
          v-model="keyword"
          placeholder="搜索项目名称、简介、成果、团队成员..."
          size="large"
          :prefix-icon="Search"
          @keyup.enter="handleSearch"
          clearable
        >
          <template #append>
            <el-button type="primary" @click="handleSearch">搜索</el-button>
          </template>
        </el-input>
      </div>

      <div v-if="searched" class="search-results">
        <p class="result-summary">共找到 {{ total }} 条结果</p>
        <el-card
          v-for="item in results"
          :key="item.id"
          shadow="hover"
          class="result-item"
          @click="router.push(`/projects/${item.id}`)"
        >
          <h3 v-html="highlight(item.title)"></h3>
          <p class="result-abstract" v-html="highlight(item.abstract || '')"></p>
          <div class="result-meta">
            <el-tag size="small">{{ item.category_name }}</el-tag>
            <span class="meta-item">负责人：{{ item.leader_name }}</span>
            <span class="meta-item">学院：{{ item.college_name }}</span>
          </div>
        </el-card>
        <el-empty v-if="results.length === 0" description="未找到匹配结果" />
      </div>
      <el-empty v-else description="输入关键词搜索项目" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { Search } from '@element-plus/icons-vue'
import { fullTextSearch } from '@/api/common'

const router = useRouter()
const keyword = ref('')
const results = ref<any[]>([])
const total = ref(0)
const searched = ref(false)

async function handleSearch() {
  if (!keyword.value.trim()) return
  searched.value = true
  try {
    const res = await fullTextSearch({ keyword: keyword.value, page: 1, page_size: 20 })
    results.value = res.data.items || res.data || []
    total.value = res.data.total || results.value.length
  } catch {
    results.value = []
    total.value = 0
  }
}

/** 关键词高亮 */
function highlight(text: string): string {
  if (!keyword.value || !text) return text
  const reg = new RegExp(`(${keyword.value})`, 'gi')
  return text.replace(reg, '<mark style="background: #fff3cd; padding: 0 2px;">$1</mark>')
}
</script>

<style scoped>
.search-box { margin-bottom: 20px; }
.result-summary { color: #909399; font-size: 14px; margin-bottom: 12px; }
.result-item { margin-bottom: 12px; cursor: pointer; }
.result-item h3 { font-size: 16px; color: #409EFF; margin-bottom: 8px; }
.result-abstract { font-size: 14px; color: #606266; margin-bottom: 8px; line-height: 1.6; }
.result-meta { display: flex; gap: 16px; align-items: center; font-size: 13px; color: #909399; }
.meta-item { font-size: 13px; }
</style>
