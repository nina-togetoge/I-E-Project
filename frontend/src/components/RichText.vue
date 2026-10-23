<!--
  富文本展示组件：对编辑器保存的 HTML 做白名单清洗后再 v-html 渲染
  用法：<RichText :content="project.innovation_points" />
-->
<template>
  <div class="rich-text" v-html="safeHtml"></div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { toSafeHtml } from '@/utils/richText'

const props = defineProps<{
  content?: string | null
}>()

const safeHtml = computed(() => toSafeHtml(props.content))
</script>

<style scoped>
.rich-text {
  line-height: 1.8;
  word-break: break-word;
}
.rich-text :deep(p) {
  margin: 0 0 8px;
}
.rich-text :deep(p:last-child) {
  margin-bottom: 0;
}
.rich-text :deep(ul),
.rich-text :deep(ol) {
  margin: 0 0 8px;
  padding-left: 22px;
}
.rich-text :deep(h1),
.rich-text :deep(h2),
.rich-text :deep(h3),
.rich-text :deep(h4) {
  margin: 12px 0 8px;
  font-weight: 600;
}
.rich-text :deep(a) {
  color: var(--el-color-primary);
  text-decoration: underline;
}
.rich-text :deep(img) {
  max-width: 100%;
  height: auto;
  border-radius: 4px;
  vertical-align: middle;
}
.rich-text :deep(table) {
  border-collapse: collapse;
  max-width: 100%;
}
.rich-text :deep(td),
.rich-text :deep(th) {
  border: 1px solid var(--el-border-color);
  padding: 4px 8px;
}
</style>
