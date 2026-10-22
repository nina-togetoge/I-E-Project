<!--
  通用文件上传组件
  支持拖拽上传、批量上传、格式与大小校验、进度条
  触发区按 listType 自适应：
    - text（默认）→「点击上传」按钮
    - picture-card → 上传卡片（“+”）
    - drag → 官方拖拽区
-->
<template>
  <div class="file-upload">
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
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖拽文件到此处，或<em>点击上传</em></div>
      </template>
      <template v-else-if="listType === 'picture-card'">
        <el-icon class="el-icon--upload"><Plus /></el-icon>
      </template>
      <el-button v-else type="primary" :icon="Upload" round>点击上传</el-button>

      <template #tip>
        <div class="el-upload__tip">支持 {{ acceptExtensions }} 格式，单文件不超过 {{ maxSize }}MB</div>
      </template>
    </el-upload>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload, UploadFilled, Plus } from '@element-plus/icons-vue'
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
  }>(),
  {
    action: '/api/files/upload',
    multiple: true,
    limit: 10,
    accept: () => ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip', '.rar', '.png', '.jpg', '.jpeg'],
    maxSize: 200,
    drag: false,
    listType: 'text',
    autoUpload: true,
    formData: () => ({}),
    name: 'file',
  }
)

const emit = defineEmits<{
  'success': [file: any]
  'remove': [file: any]
  'change': [files: UploadUserFile[]]
}>()

const uploadRef = ref()
const fileList = ref<UploadUserFile[]>([])

const userStore = useUserStore()

const headers = computed(() => ({
  Authorization: `Bearer ${userStore.accessToken}`,
}))

const acceptStr = computed(() => props.accept.join(','))
const acceptExtensions = computed(() => props.accept.join(' / '))

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

.file-upload :deep(.el-upload-list) {
  margin-top: 4px;
}

.file-upload :deep(.el-upload__tip) {
  color: #909399;
  font-size: 12px;
  line-height: 1.6;
  margin-top: 6px;
}

/* 拖拽区在非受限宽度下铺满，小屏友好 */
.file-upload :deep(.el-upload-dragger) {
  width: 100%;
}
</style>