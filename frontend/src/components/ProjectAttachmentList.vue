<!--
  项目附件列表组件（展示+预览+下载）
  用法：<ProjectAttachmentList :attachments="project.attachments" />
-->
<template>
  <div v-if="attachments && attachments.length > 0" class="attachment-list">
    <div
      v-for="att in attachments"
      :key="att.id"
      class="attachment-item"
    >
      <span class="att-icon">{{ fileIcon(att.file_name) }}</span>
      <div class="att-info">
        <span class="att-name" :title="att.file_name">{{ att.file_name }}</span>
        <span class="att-meta">{{ formatFileSize(att.file_size) }} · {{ att.uploader_name }} 上传</span>
      </div>
      <div class="att-actions">
        <el-button link type="primary" size="small" @click="handlePreview(att)">预览</el-button>
        <el-button link type="primary" size="small" @click="handleDownload(att)">下载</el-button>
      </div>
    </div>
  </div>
  <el-empty v-else description="暂无附件" :image-size="60" />
</template>

<script setup lang="ts">
defineProps<{
  attachments: any[]
}>()

function fileIcon(fileName: string): string {
  const ext = (fileName.split('.').pop() || '').toLowerCase()
  const map: Record<string, string> = {
    pdf: '📄', doc: '📝', docx: '📝', xls: '📊', xlsx: '📊',
    ppt: '📽️', pptx: '📽️', png: '🖼️', jpg: '🖼️', jpeg: '🖼️', gif: '🖼️',
    zip: '📦', rar: '📦', '7z': '📦', txt: '📃', md: '📃',
  }
  return map[ext] || '📎'
}

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

function handlePreview(att: any) {
  window.open(att.preview_url, '_blank')
}

function handleDownload(att: any) {
  window.open(att.download_url, '_blank')
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
