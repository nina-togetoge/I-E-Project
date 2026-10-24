<!--
  ==== RichText ====
  职责：富文本只读展示组件，对编辑器保存的 HTML 做白名单清洗后再用 v-html 渲染。
  复用：项目详情、申报书预览、评审材料、驳回理由等所有展示 RichEditor 产出内容的位置。
        用法：<RichText :content="project.innovation_points" />
  契约：props：content（string | null | undefined，空值按空串渲染）；
        无 emit、无插槽、无交互。
  注意：1) 必须经 toSafeHtml 清洗，严禁直接 v-html 后端原始字符串，防止 XSS；
        2) 清洗会移除 script/style/iframe 等危险标签、非白名单属性与危险协议链接，
           图片仅允许本站附件直链或 http(s) 地址；
        3) 历史纯文本会被转义并按换行转成 <br>，因此无需调用方区分内容类型。
-->
<template>
  <!-- 区块：只读富文本容器；safeHtml 已完成标签与属性清洗 -->
  <div class="rich-text" v-html="safeHtml"></div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { toSafeHtml } from '@/utils/richText'

// ==================== props ====================
/**
 * 后端保存的富文本 HTML 字符串。
 * 允许为空（草稿或未填写），组件内部统一按空串处理，不渲染任何内容。
 */
const props = defineProps<{
  content?: string | null
}>()

// ==================== 计算属性 ====================
/**
 * 清洗后的安全 HTML：由 toSafeHtml 过滤标签白名单、属性白名单与危险协议。
 * 依赖 content，父组件传入内容变化时自动重新计算，是 v-html 的唯一数据源。
 */
const safeHtml = computed(() => toSafeHtml(props.content))
</script>

<style scoped>
/* 容器：宽松行高，长文档阅读更舒适；长英文/URL 强制断行防止撑破布局 */
.rich-text {
  line-height: 1.8;
  word-break: break-word;
}
/* 段落：保留段间距，末段去掉多余底部留白，避免容器出现双倍空隙 */
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
/* 链接：沿用主题主色并加下划线，明确可点击语义 */
.rich-text :deep(a) {
  color: var(--el-color-primary);
  text-decoration: underline;
}
/* 图片：自适应容器宽度，避免富文本中的大图横向溢出 */
.rich-text :deep(img) {
  max-width: 100%;
  height: auto;
  border-radius: 4px;
  vertical-align: middle;
}
/* 表格：合并边框并限制最大宽度，保证经费预算等表格在窄屏下仍可读 */
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
