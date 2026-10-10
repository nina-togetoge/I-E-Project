<template>
  <el-button link type="primary" size="small" @click="dialogVisible = true">📝 插入评语模板</el-button>
  <el-dialog
    v-model="dialogVisible"
    title="选择评语模板"
    width="520px"
    center
    :close-on-click-modal="true"
    append-to-body
    class="template-picker-dialog"
  >
    <el-tabs v-model="activeTab">
      <el-tab-pane label="通过模板" name="pass">
        <div class="template-list">
          <div
            v-for="t in passTemplates"
            :key="t.label"
            class="template-item"
            @click="handleSelect(t.text)"
          >
            <span class="template-label">{{ t.label }}</span>
            <span class="template-text">{{ t.text }}</span>
          </div>
        </div>
      </el-tab-pane>
      <el-tab-pane label="驳回模板" name="reject">
        <div class="template-list">
          <div
            v-for="t in rejectTemplates"
            :key="t.label"
            class="template-item"
            @click="handleSelect(t.text)"
          >
            <span class="template-label">{{ t.label }}</span>
            <span class="template-text">{{ t.text }}</span>
          </div>
        </div>
      </el-tab-pane>
      <el-tab-pane label="通用" name="common">
        <div class="template-list">
          <div
            v-for="t in commonTemplates"
            :key="t.label"
            class="template-item"
            @click="handleSelect(t.text)"
          >
            <span class="template-label">{{ t.label }}</span>
            <span class="template-text">{{ t.text }}</span>
          </div>
          <div v-if="commonTemplates.length === 0" class="empty-tip">暂无通用模板</div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { reviewTemplates } from '@/data/reviewTemplates'

const emit = defineEmits<{
  select: [text: string]
}>()

const dialogVisible = ref(false)
const activeTab = ref<'pass' | 'reject' | 'common'>('pass')

const passTemplates = computed(() => reviewTemplates.filter((t) => t.category === 'pass'))
const rejectTemplates = computed(() => reviewTemplates.filter((t) => t.category === 'reject'))
const commonTemplates = computed(() => reviewTemplates.filter((t) => t.category === 'common'))

function handleSelect(text: string) {
  emit('select', text)
  dialogVisible.value = false
}
</script>

<style scoped>
:deep(.template-picker-dialog) {
  top: 50% !important;
  margin-top: 0 !important;
  transform: translateY(-50%);
}
.template-list {
  max-height: 360px;
  overflow-y: auto;
}
.template-item {
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.2s;
  margin-bottom: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.template-item:hover {
  background-color: var(--el-color-primary-light-9);
}
.template-label {
  font-size: 12px;
  color: var(--el-color-primary);
  font-weight: 500;
}
.template-text {
  font-size: 13px;
  color: #606266;
  line-height: 1.5;
}
.empty-tip {
  text-align: center;
  color: #909399;
  padding: 20px 0;
  font-size: 13px;
}
</style>
