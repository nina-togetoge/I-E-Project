<!--
  项目附件列表组件（ProjectAttachmentList）
  面向角色：所有可查看项目详情/表单的用户；删除按钮仅在使用方显式开启时可操作。
  核心功能：展示附件的图标、文件名、大小、上传人，并提供预览与下载；
           无附件时显示空状态，避免页面出现空白区域。
  调用 API：本组件不直接请求，预览/下载通过 window.open 打开后端文件地址；
           URL 为空时回退到 /api/files/preview/{id} 与 /api/files/download/{id}。
  关键权限 / 安全约束：
    - 文件接口受鉴权保护，而 window.open 无法携带 Authorization 头，
      因此统一在 URL 后追加 ?token= 使用后端兜底鉴权；
    - 预览与下载均使用 noopener/noreferrer，防止新窗口通过 window.opener 反向操作本页；
    - 删除按钮由 deletable 控制，默认关闭，只有编辑场景才由父组件打开；
      本组件不判断角色，权限必须由使用方先行确认。
  特别注意：文件图标按扩展名映射为固定字符（含表情符号），属于既有展示字符串，
           不要改动；未知扩展名回退为通用附件图标。
-->
<template>
  <!-- 有附件时逐条展示；attachments 为空或未加载时走下方的空状态 -->
  <div v-if="attachments && attachments.length > 0" class="attachment-list">
    <!-- 单条附件：图标固定宽度，信息区自适应并省略过长文件名 -->
    <div
      v-for="att in attachments"
      :key="att.id"
      class="attachment-item"
    >
      <span class="att-icon">{{ fileIcon(att.file_name) }}</span>
      <div class="att-info">
        <span class="att-name" :title="att.file_name">{{ att.file_name }}</span>
        <!-- 元信息：大小与上传人，帮助用户判断文件是否为目标版本 -->
        <span class="att-meta">{{ formatFileSize(att.file_size) }} · {{ att.uploader_name }} 上传</span>
      </div>
      <div class="att-actions">
        <!-- 预览/下载对所有可见用户开放；实际鉴权由后端 token 校验 -->
        <el-button link type="primary" size="small" @click="handlePreview(att)">预览</el-button>
        <el-button link type="primary" size="small" @click="handleDownload(att)">下载</el-button>
        <!-- 删除仅在父组件开启 deletable 时出现（编辑态），避免只读页面误删附件 -->
        <el-button v-if="deletable" link type="danger" size="small" @click="emit('remove', att)">删除</el-button>
      </div>
    </div>
  </div>
  <!-- 空状态：不影响布局，仅提示暂无附件 -->
  <el-empty v-else description="暂无附件" :image-size="60" />
</template>

<script setup lang="ts">
import { useUserStore } from '@/store/user'

// ==================== Props / Emits ====================

withDefaults(
  defineProps<{
    /** 附件数组，字段至少包含 id、file_name、file_size、uploader_name */
    attachments: any[]
    /** 是否显示删除按钮（编辑场景传入 true） */
    deletable?: boolean
  }>(),
  { deletable: false }
)

const emit = defineEmits<{
  /** 点击删除时把整条附件交给父组件，由父组件决定是否调用接口及如何刷新 */
  'remove': [att: any]
}>()

// ==================== 鉴权 ====================

const userStore = useUserStore()

/**
 * 为受鉴权保护的文件 URL 追加 token。
 * 说明：window.open 无法携带 Authorization 头，后端已对
 * /api/files/download、/api/files/preview 两个前缀开放 ?token= 兜底鉴权。
 * 失败处理：url 为空或用户无 token 时原样返回，交由后端返回明确的未授权响应。
 * @param url 文件预览/下载地址
 */
function withToken(url: string): string {
  if (!url) return url
  const token = userStore.accessToken
  if (!token) return url
  const sep = url.includes('?') ? '&' : '?'
  return `${url}${sep}token=${encodeURIComponent(token)}`
}

// ==================== 展示辅助 ====================

/**
 * 根据文件名扩展名返回图标字符。
 * 说明：仅做展示，不校验文件真实类型；未知扩展名回退为通用附件图标。
 * @param fileName 原始文件名
 */
function fileIcon(fileName: string): string {
  const ext = (fileName.split('.').pop() || '').toLowerCase()
  const map: Record<string, string> = {
    pdf: '📄', doc: '📝', docx: '📝', xls: '📊', xlsx: '📊',
    ppt: '📽️', pptx: '📽️', png: '🖼️', jpg: '🖼️', jpeg: '🖼️', gif: '🖼️',
    zip: '📦', rar: '📦', '7z': '📦', txt: '📃', md: '📃',
  }
  return map[ext] || '📎'
}

/**
 * 把字节数格式化为易读大小。
 * 规则：按 1024 进位；B 不保留小数，KB/MB/GB 保留一位小数。
 * @param bytes 文件字节数，0 或缺失时显示 0 B
 */
function formatFileSize(bytes: number): string {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let size = bytes
  while (size >= 1024 && i < units.length - 1) {
    size /= 1024
    i++
  }
  return `${size.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

// ==================== 文件操作 ====================

/**
 * 预览附件。
 * 优先使用后端返回的 preview_url，缺失时按 id 拼默认地址；
 * 副作用：打开新窗口，因此必须带 token 且禁止 opener 引用。
 * 失败处理：新窗口中的异常由后端页面提示，本组件无法感知。
 * @param att 附件对象
 */
function handlePreview(att: any) {
  const url = att.preview_url || `/api/files/preview/${att.id}`
  window.open(withToken(url), '_blank', 'noopener,noreferrer')
}

/**
 * 下载附件。
 * 与预览共用鉴权拼接逻辑，区别是使用 download_url/下载前缀触发浏览器下载行为。
 * 副作用：打开新窗口并开始下载，不改变当前页面状态。
 * @param att 附件对象
 */
function handleDownload(att: any) {
  const url = att.download_url || `/api/files/download/${att.id}`
  window.open(withToken(url), '_blank', 'noopener,noreferrer')
}
</script>

<style scoped>
.attachment-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.attachment-item {
  display: flex;
  align-items: center;
  padding: 10px 14px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
  transition: background-color 0.2s;
}
.attachment-item:hover {
  background: var(--el-color-primary-light-9);
}
.att-icon {
  font-size: 22px;
  margin-right: 12px;
}
.att-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.att-name {
  font-size: 14px;
  color: #303133;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.att-meta {
  font-size: 12px;
  color: #909399;
}
.att-actions {
  display: flex;
  gap: 8px;
  margin-left: 12px;
}
</style>
