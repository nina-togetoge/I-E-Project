<!--
  ==== FileUpload ====
  职责：通用附件上传组件，支持拖拽/按钮/卡片三种触发形态、批量上传、格式与大小校验、
        上传进度与结果提示。
  复用：项目申报书附件（商业计划书、证明材料）、中期检查材料、结题材料、成果佐证等
        所有需要上传实体文件的表单。
  契约：props：action / multiple / limit / accept / maxSize / drag / listType /
              autoUpload / formData / name；
        emits：success（单个文件上传成功，载荷为后端返回的文件信息，父组件据此记录附件 id）、
               remove（移除文件，载荷为该文件）、
               change（列表变化，载荷为完整文件列表）；
        暴露：submit() / clear() / fileList。
  注意：1) 文件本体由后端落盘（Docker 卷），前端只保存后端返回的附件 id；
        2) 默认内置 Authorization 头，上传接口走登录态鉴权；
        3) 校验在 beforeUpload 阶段完成，不合格文件不会真正发出请求；
        4) 默认接受 pdf/word/excel/压缩包/图片，单文件上限 200MB。
-->
<template>
  <div class="file-upload">
    <!-- 区块：上传器主体，事件与配置全部透传给 el-upload，校验由 beforeUpload 统一拦截 -->
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
      <!-- 触发区三态：拖拽区优先，其次图片卡片，最后退化为普通按钮 -->
      <template v-if="drag">
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖拽文件到此处，或<em>点击上传</em></div>
      </template>
      <template v-else-if="listType === 'picture-card'">
        <el-icon class="el-icon--upload"><Plus /></el-icon>
      </template>
      <el-button v-else type="primary" :icon="Upload" round>点击上传</el-button>

      <!-- 底部提示：把 accept 与 maxSize 转成可读文案，让用户上传前就知道限制 -->
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

// ==================== props / emits ====================
/**
 * 上传配置。与文件相关的限制都在这里声明，避免调用方各自写一套校验。
 */
const props = withDefaults(
  defineProps<{
    /** 上传接口地址，默认走后端统一附件上传接口 /api/files/upload */
    action?: string
    /** 是否允许多选，默认 true；单附件场景（如项目封面）应传 false */
    multiple?: boolean
    /** 单次最多可选文件数，默认 10，超出时由 handleExceed 提示 */
    limit?: number
    /** 允许的扩展名数组（含点号），默认覆盖 pdf/word/excel/压缩包/常见图片 */
    accept?: string[]
    /** 单文件大小上限，单位 MB，默认 200，也在提示文案中展示 */
    maxSize?: number
    /** 是否启用拖拽上传区，默认 false（普通按钮形态） */
    drag?: boolean
    /** 列表展示形态，默认 text；图片附件可用 picture-card */
    listType?: 'text' | 'picture' | 'picture-card'
    /** 是否选择后立即上传，默认 true；false 时需父组件调用 submit() */
    autoUpload?: boolean
    /** 随文件一并提交的额外表单字段（如项目 id、附件类型） */
    formData?: Record<string, any>
    /** 上传接口接收的文件字段名，默认 file，需与后端约定一致 */
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

/**
 * 对外事件契约：
 * - success：单文件上传且后端返回 code=200 时触发，载荷为 response.data（含附件 id / URL），
 *   父组件通常把该 id 写进表单的附件字段；
 * - remove：用户删除已选/已上传文件时触发，载荷为被删文件，父组件据此同步后端解绑；
 * - change：文件列表任何变化（新增、成功、删除）时触发，载荷为完整列表，适合做整体校验。
 */
const emit = defineEmits<{
  'success': [file: any]
  'remove': [file: any]
  'change': [files: UploadUserFile[]]
}>()

// ==================== 状态与依赖 ====================
/** el-upload 实例引用，用于暴露 submit / clearFiles */
const uploadRef = ref()
/** 组件内部维护的文件列表，与 el-upload 双向同步，并通过 defineExpose 对外暴露 */
const fileList = ref<UploadUserFile[]>([])

/** 用户 store，仅用于取登录 token 拼装上传请求头 */
const userStore = useUserStore()

// ==================== 计算属性 ====================
/** 上传请求头：带 Bearer token，附件接口需要登录态 */
const headers = computed(() => ({
  Authorization: `Bearer ${userStore.accessToken}`,
}))

/** 传给 el-upload 的 accept 字符串（逗号分隔），用于系统文件选择框过滤 */
const acceptStr = computed(() => props.accept.join(','))
/** 提示文案用的可读格式列表（斜杠分隔） */
const acceptExtensions = computed(() => props.accept.join(' / '))

// ==================== 上传校验与回调 ====================
/**
 * 上传前置校验：扩展名白名单 + 单文件大小上限。
 * @param file 浏览器选择的文件对象
 * @returns true 放行；false 阻断上传并弹出具体原因
 * 副作用：校验失败时通过 ElMessage 提示用户。
 * 注意：扩展名取自文件名末段，不校验 MIME，Word/Excel 的 MIME 在各浏览器不统一。
 */
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

/**
 * 文件列表变化回调：选择、上传完成、删除都会触发，保持内部列表与组件 DOM 一致。
 * @param _file 本次变化的文件（此处不使用）
 * @param files 变化后的完整文件列表
 * 副作用：更新 fileList 并向外触发 change。
 */
const handleChange: UploadProps['onChange'] = (_file: UploadFile, files: UploadUserFile[]) => {
  fileList.value = files
  emit('change', files)
}

/**
 * 单文件上传成功回调：按后端统一响应结构判断 code。
 * @param response 后端响应，code=200 表示成功，data 中带附件 id 等信息
 * @param file 本次上传的文件
 * 副作用：成功时提示、向外触发 success 与 change；失败时提示后端 message。
 */
const handleSuccess = (response: any, file: UploadFile) => {
  if (response.code === 200) {
    ElMessage.success(`${file.name} 上传成功`)
    emit('success', response.data)
    emit('change', fileList.value)
  } else {
    ElMessage.error(response.message || '上传失败')
  }
}

/**
 * 上传失败回调（网络错误、超时、网关异常等）。
 * @param _error 原始错误对象，此处不细分
 * @param file 失败的文件
 * 副作用：弹出失败提示；文件会由 el-upload 标记为失败态，可重试或移除。
 */
const handleError = (_error: any, file: UploadFile) => {
  ElMessage.error(`${file.name} 上传失败`)
}

/**
 * 移除文件回调：用户点击列表中的删除按钮时触发。
 * @param file 被移除的文件
 * @param files 移除后的剩余列表
 * 副作用：更新 fileList，向外触发 remove（父组件据此解绑已保存的附件）与 change。
 */
const handleRemove = (file: UploadFile, files: UploadUserFile[]) => {
  fileList.value = files
  emit('remove', file)
  emit('change', files)
}

/**
 * 超出数量上限回调：仅提示，不自动替换已有文件，避免误删用户已选内容。
 * 副作用：弹出警告消息。
 */
const handleExceed = () => {
  ElMessage.warning(`最多只能上传 ${props.limit} 个文件`)
}

// ==================== 对外方法 ====================
/**
 * 手动提交待上传文件，仅在 autoUpload=false 时使用。
 * 副作用：触发 el-upload 的实际上传流程。
 */
function submit() {
  uploadRef.value?.submit()
}

/**
 * 清空已选/已上传文件列表。
 * 副作用：清空 el-upload 内部列表与组件 fileList；不会调用后端删除接口，
 * 已落盘的附件需由父组件按业务逻辑解绑。
 */
function clear() {
  uploadRef.value?.clearFiles()
  fileList.value = []
}

/** 暴露给父组件的实例能力：手动提交、清空、读取当前列表 */
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