<!--
  通用文件上传组件
  支持拖拽上传、批量上传、格式与大小校验、进度条
-->
<template>
  <div class="file-upload">
    <div
      class="drop-zone"
      :class="{ 'is-dragging': isDragging }"
      @dragover.prevent
      @dragenter.prevent="isDragging = true"
      @dragleave="isDragging = false"
      @drop.prevent="handleDrop"
    >
      <div v-if="!hideDropHint" class="drop-hint">
        <el-icon class="drop-icon"><UploadFilled /></el-icon>
        <p class="drop-text">
          <span>支持拖拽文件到此</span>
          <span class="drop-or">，或</span>
          <span>点击下方按钮选择</span>
        </p>
      </div>
      <el-upload
        ref="uploadRef"
        :action="action"
        :headers="headers"
        :multiple="multiple"
        :limit="limit"
        :accept="acceptStr"
        :max-size="maxSize"
        :name="name"
        :data="formData"
        :before-upload="beforeUpload"
        :on-success="handleSuccess"
        :on-error="handleError"
        :on-remove="handleRemove"
        :on-exceed="handleExceed"
        :file-list="fileList"
        :drag="drag"
        :list-type="listType"
        :auto-upload="autoUpload"
        :on-change="handleChange"
      >
        <template v-if="drag">
          <el-icon class="el-icon--upload"><upload-filled /></el-icon>
          <div class="el-upload__text">拖拽文件到此处，或<em>点击上传</em></div>
        </template>
        <el-button v-else type="primary" :icon="Upload">点击上传</el-button>

        <template #tip>
          <div class="el-upload__tip">
            支持 {{ acceptExtensions }} 格式，单文件不超过 {{ maxSizeMB }}MB
          </div>
        </template>
      </el-upload>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload, UploadFilled } from '@element-plus/icons-vue'
import type { UploadFile, UploadProps, UploadUserFile } from 'element-plus'
import { useUserStore } from '@/store/user'
import { bytesToMB, formatSize } from '@/utils/format'

const props = withDefaults(
  defineProps<{
    action?: string
    multiple?: boolean
    limit?: number
    accept?: string[]
    maxSize?: number
    drag?: boolean
    listType?: 'text' | 'picture' | 'picture-card'
    autoUpload?: boolean
    formData?: Record<string, any>
    name?: string
    hideDropHint?: boolean
  }>(),
  {
    action: '/api/files/upload',
    multiple: true,
    limit: 10,
    accept: () => ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip', '.rar', '.png', '.jpg', '.jpeg'],
    maxSize: 50,
    drag: false,
    listType: 'text',
    autoUpload: true,
    formData: () => ({}),
    name: 'file',
    hideDropHint: false,
  }
)

const emit = defineEmits<{
  'success': [file: any]
  'remove': [file: any]
  'change': [files: UploadUserFile[]]
}>()

const uploadRef = ref()
const fileList = ref<UploadUserFile[]>([])
const isDragging = ref(false)

const userStore = useUserStore()

const headers = computed(() => ({
  Authorization: `Bearer ${userStore.accessToken}`,
}))

const acceptStr = computed(() => props.accept.join(','))
const acceptExtensions = computed(() => props.accept.join(' / '))
const maxSizeMB = computed(() => props.maxSize)

function handleFileChange(files: FileList | File[]) {
  const arr = Array.from(files)
  for (const file of arr) {
    uploadRef.value?.handleStart?.(file)
  }
}

function handleDrop(e: DragEvent) {
  isDragging.value = false
  const files = e.dataTransfer?.files
  if (files && files.length > 0) {
    handleFileChange(files)
  }
}

const beforeUpload: UploadProps['beforeUpload'] = (file: File) => {
  const ext = '.' + file.name.split('.').pop()?.toLowerCase()
  if (props.accept.length > 0 && !props.accept.includes(ext)) {
    ElMessage.error(`不支持的文件格式：${ext}，仅支持 ${acceptExtensions.value}`)
    return false
  }
  const sizeMB = bytesToMB(file.size)
  if (sizeMB > props.maxSize) {
    ElMessage.error(`文件大小超过限制：${formatSize(file.size)}，最大允许 ${props.maxSize}MB`)
    return false
  }
  return true
}

const handleChange: UploadProps['onChange'] = (_file: UploadFile, files: UploadUserFile[]) => {
  fileList.value = files
  emit('change', files)
}

const handleSuccess = (response: any, file: UploadFile) => {
  if (response.code === 200) {
    ElMessage.success(`${file.name} 上传成功`)
    emit('success', response.data)
    emit('change', fileList.value)
  } else {
    ElMessage.error(response.message || '上传失败')
  }
}

const handleError = (_error: any, file: UploadFile) => {
  ElMessage.error(`${file.name} 上传失败`)
}

const handleRemove = (file: UploadFile, files: UploadUserFile[]) => {
  fileList.value = files
  emit('remove', file)
  emit('change', files)
}

const handleExceed = () => {
  ElMessage.warning(`最多只能上传 ${props.limit} 个文件`)
}

function submit() {
  uploadRef.value?.submit()
}

function clear() {
  uploadRef.value?.clearFiles()
  fileList.value = []
}

defineExpose({ submit, clear, fileList })
</script>

<style scoped>
.file-upload {
  width: 100%;
}

.drop-zone {
  width: 100%;
  padding: 20px;
  border: 2px dashed var(--border-color, #e4e7ed);
  border-radius: 8px;
  transition: all 0.25s ease;
  background: transparent;
}

.drop-zone.is-dragging {
  border-style: solid;
  border-color: var(--primary-color, #409EFF);
  background-color: color-mix(in srgb, var(--primary-color, #409EFF) 10%, transparent);
}

.drop-hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  margin-bottom: 12px;
  color: var(--text-color-secondary, #909399);
}

.drop-icon {
  font-size: 32px;
  color: var(--primary-color, #409EFF);
  margin-bottom: 8px;
  opacity: 0.75;
}

.drop-text {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
}

.drop-or {
  margin: 0 2px;
  opacity: 0.7;
}
</style>
