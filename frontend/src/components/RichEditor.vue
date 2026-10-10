<template>
  <div class="rich-editor" :style="{ width: width }">
    <div class="editor-toolbar">
      <el-button-group>
        <el-button
          size="small"
          :type="activeFormats.bold ? 'primary' : 'default'"
          @click="exec('bold')"
          title="粗体"
        >
          <b>B</b>
        </el-button>
        <el-button
          size="small"
          :type="activeFormats.italic ? 'primary' : 'default'"
          @click="exec('italic')"
          title="斜体"
        >
          <i>I</i>
        </el-button>
        <el-button
          size="small"
          :type="activeFormats.underline ? 'primary' : 'default'"
          @click="exec('underline')"
          title="下划线"
        >
          <u>U</u>
        </el-button>
        <el-button
          size="small"
          :type="activeFormats.strikeThrough ? 'primary' : 'default'"
          @click="exec('strikeThrough')"
          title="删除线"
        >
          <s>S</s>
        </el-button>
      </el-button-group>

      <el-divider direction="vertical" />

      <el-button-group>
        <el-button size="small" @click="exec('insertUnorderedList')" title="无序列表">
          • 列表
        </el-button>
        <el-button size="small" @click="exec('insertOrderedList')" title="有序列表">
          1. 列表
        </el-button>
      </el-button-group>

      <el-divider direction="vertical" />

      <el-button-group>
        <el-button size="small" @click="exec('justifyLeft')" title="左对齐">
          左
        </el-button>
        <el-button size="small" @click="exec('justifyCenter')" title="居中">
          中
        </el-button>
        <el-button size="small" @click="exec('justifyRight')" title="右对齐">
          右
        </el-button>
      </el-button-group>

      <el-divider direction="vertical" />

      <el-button size="small" @click="insertLink" title="插入链接">🔗</el-button>
      <el-button size="small" @click="insertImage" title="插入图片">🖼️</el-button>
      <el-button size="small" @click="exec('removeFormat')" title="清除格式">✕ 格式</el-button>
    </div>

    <div
      ref="editorRef"
      class="editor-content"
      :style="{ minHeight: minHeight }"
      :data-placeholder="placeholder"
      contenteditable="true"
      @input="handleInput"
      @paste="handlePaste"
      @keyup="updateActiveFormats"
      @mouseup="updateActiveFormats"
    ></div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUpdate, watch, nextTick } from 'vue'

const props = withDefaults(
  defineProps<{
    modelValue: string
    minHeight?: string
    width?: string
    placeholder?: string
  }>(),
  {
    minHeight: '200px',
    width: '100%',
    placeholder: '',
  }
)
const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const editorRef = ref<HTMLDivElement>()
const activeFormats = ref({
  bold: false,
  italic: false,
  underline: false,
  strikeThrough: false,
})

let isInternalSet = false
let savedRange: Range | null = null

function saveSelection() {
  const sel = window.getSelection()
  if (sel && sel.rangeCount > 0) {
    savedRange = sel.getRangeAt(0).cloneRange()
  }
}

function restoreSelection() {
  if (!savedRange || !editorRef.value) return
  const sel = window.getSelection()
  if (!sel) return
  sel.removeAllRanges()
  try {
    sel.addRange(savedRange)
  } catch (_) {}
}

function exec(cmd: string, arg?: string) {
  editorRef.value?.focus()
  restoreSelection()
  document.execCommand(cmd, false, arg)
  saveSelection()
  handleInput()
  updateActiveFormats()
}

async function insertLink() {
  const { value: url } = await (window as any).ElMessageBox?.prompt?.({
    title: '插入链接',
    message: '请输入链接URL：',
    inputPattern: /^https?:\/\/.+/,
    inputErrorMessage: '请输入以 http:// 或 https:// 开头的有效链接',
  }) ?? (() => {
    const input = prompt('请输入链接URL（以 http:// 或 https:// 开头）：')
    return { value: input }
  })()
  if (url) {
    exec('createLink', url)
  }
}

async function insertImage() {
  const { value: url } = await (window as any).ElMessageBox?.prompt?.({
    title: '插入图片',
    message: '请输入图片URL：',
  }) ?? (() => {
    const input = prompt('请输入图片URL：')
    return { value: input }
  })()
  if (url) {
    exec('insertImage', url)
  }
}

function handleInput() {
  if (isInternalSet) return
  saveSelection()
  const html = editorRef.value?.innerHTML || ''
  emit('update:modelValue', html)
}

function handlePaste(e: ClipboardEvent) {
  e.preventDefault()
  const text = e.clipboardData?.getData('text/plain') || ''
  editorRef.value?.focus()
  restoreSelection()
  document.execCommand('insertText', false, text)
  saveSelection()
  handleInput()
}

function updateActiveFormats() {
  try {
    activeFormats.value = {
      bold: document.queryCommandState('bold'),
      italic: document.queryCommandState('italic'),
      underline: document.queryCommandState('underline'),
      strikeThrough: document.queryCommandState('strikeThrough'),
    }
  } catch (_) {}
}

onBeforeUpdate(() => {
  saveSelection()
})

watch(
  () => props.modelValue,
  async (val) => {
    await nextTick()
    if (!editorRef.value) return
    if (editorRef.value.innerHTML !== val) {
      isInternalSet = true
      editorRef.value.innerHTML = val || ''
      isInternalSet = false
    }
  },
  { immediate: true }
)

onMounted(async () => {
  await nextTick()
  if (editorRef.value && props.modelValue) {
    isInternalSet = true
    editorRef.value.innerHTML = props.modelValue
    isInternalSet = false
  }
})
</script>

<style scoped>
.rich-editor {
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  overflow: hidden;
  background: #fff;
}

.rich-editor:focus-within {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.1);
}

.editor-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  padding: 8px 10px;
  border-bottom: 1px solid #ebeef5;
  background: #fafafa;
}

.editor-toolbar :deep(.el-divider--vertical) {
  height: 22px;
  margin: 0 6px;
}

.editor-content {
  padding: 12px;
  line-height: 1.7;
  color: #303133;
  outline: none;
  word-break: break-word;
}

.editor-content:empty::before {
  content: attr(data-placeholder);
  color: #a8abb2;
  pointer-events: none;
}

.editor-content :deep(p) {
  margin: 0 0 8px 0;
}

.editor-content :deep(ul),
.editor-content :deep(ol) {
  padding-left: 24px;
  margin: 0 0 8px 0;
}

.editor-content :deep(a) {
  color: var(--el-color-primary);
  text-decoration: underline;
}

.editor-content :deep(img) {
  max-width: 100%;
  height: auto;
  border-radius: 4px;
}
</style>
