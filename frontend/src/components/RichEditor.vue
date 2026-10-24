<!--
  ==== RichEditor ====
  职责：轻量富文本编辑器，基于 contenteditable + document.execCommand 实现，
        提供加粗/斜体/下划线/删除线、有序/无序列表、对齐、清除格式、
        粘贴纯文本化与本地图片上传插入。
  复用：项目申报书的「项目简介」「创新点」「实施方案」等长文本字段、
        评审意见/驳回理由输入等表单场景。
  契约：v-model（modelValue）双向绑定 HTML 字符串；
        props：minHeight / width / placeholder；
        emits：update:modelValue（正文变化，载荷为最新 innerHTML）；
        无插槽。
  注意：1) 保存的是 HTML 片段，展示端必须经 RichText 白名单清洗后再渲染；
        2) 图片先上传到后端，正文中只保留图片直链，不持有二进制本体；
        3) 工具栏 mousedown 已阻止默认行为，以保证编辑区选区不丢失。
-->
<template>
  <div class="rich-editor" :style="{ width: width }">
    <!-- 区块：格式工具栏（mousedown.prevent 防止点击按钮时编辑区失焦、选区被清空） -->
    <div class="editor-toolbar" @mousedown.prevent>
      <!-- 行内格式组：加粗 / 斜体 / 下划线 / 删除线，按钮主色高亮表示光标处已应用该格式 -->
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

      <!-- 块级格式组：无序列表 / 有序列表，常用于项目书中的研究内容、实施步骤 -->
      <el-button-group>
        <el-button size="small" @click="exec('insertUnorderedList')" title="无序列表">
          • 列表
        </el-button>
        <el-button size="small" @click="exec('insertOrderedList')" title="有序列表">
          1. 列表
        </el-button>
      </el-button-group>

      <el-divider direction="vertical" />

      <!-- 段落对齐组：左 / 居中 / 右，对应 execCommand 的 justify* 命令 -->
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

      <!-- 附件与清理：插入图片（走上传接口后回填直链）、清除选区内的行内格式 -->
      <el-button size="small" @click="insertImage" title="上传并插入图片">🖼️</el-button>
      <el-button size="small" @click="exec('removeFormat')" title="清除格式">✕ 格式</el-button>
    </div>

    <!-- 区块：可编辑正文区
         placeholder 通过 data-placeholder 传给 CSS，由 :empty::before 渲染，
         这样无需额外占位节点，也不会污染保存的 HTML -->
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
import { ElMessage } from 'element-plus'
import { uploadFiles } from '@/api/common'

// ==================== props / emits ====================
/**
 * 编辑器对外契约。v-model 绑定的是 HTML 片段而非纯文本，
 * 父组件按字符串保存，展示时交给 RichText 做白名单清洗。
 */
const props = withDefaults(
  defineProps<{
    /** 双向绑定的正文 HTML；为空串时正文区显示占位符 */
    modelValue: string
    /** 正文区最小高度，默认 200px，用于项目书等多行文本场景 */
    minHeight?: string
    /** 编辑器整体宽度，默认 100%，可传固定宽度嵌入窄容器 */
    width?: string
    /** 正文为空时的提示文案，通过 data-placeholder 交给 CSS 渲染 */
    placeholder?: string
  }>(),
  {
    minHeight: '200px',
    width: '100%',
    placeholder: '',
  }
)
/**
 * 唯一的对外事件：正文发生变化时触发（用户输入 / 工具栏命令 / 粘贴 / 插图）。
 * 载荷为最新的 innerHTML；父组件通常直接写入表单字段或项目草稿。
 */
const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

// ==================== 状态 ====================
/** 正文区 DOM 引用，所有 execCommand 与 innerHTML 读写都依赖它 */
const editorRef = ref<HTMLDivElement>()
/** 工具栏按钮的激活态，随光标所在位置的格式实时刷新 */
const activeFormats = ref({
  bold: false,
  italic: false,
  underline: false,
  strikeThrough: false,
})

/**
 * 标记本次 innerHTML 写入是否由组件自身发起（回填 props），
 * 用于在 handleInput 中跳过重复 emit，避免父子双向更新抖动。
 */
let isInternalSet = false
/** 上一次有效选区；工具栏操作、粘贴、插图前用它恢复光标，防止命令作用到错误位置 */
let savedRange: Range | null = null

// ==================== 选区管理 ====================
/**
 * 缓存当前浏览器选区（克隆副本），供 restoreSelection 恢复。
 * 副作用：仅更新内部变量 savedRange，不修改 DOM。
 */
function saveSelection() {
  const sel = window.getSelection()
  if (sel && sel.rangeCount > 0) {
    savedRange = sel.getRangeAt(0).cloneRange()
  }
}

/**
 * 把缓存的选区重新应用到编辑器。
 * 副作用：修改全局 Selection（先清空再加回保存的 Range）；缓存缺失或 Range 已失效时静默返回。
 */
function restoreSelection() {
  if (!savedRange || !editorRef.value) return
  const sel = window.getSelection()
  if (!sel) return
  sel.removeAllRanges()
  try {
    sel.addRange(savedRange)
  } catch (_) {}
}

// ==================== 编辑命令 ====================
/**
 * 执行浏览器原生编辑命令，并把结果同步回组件状态。
 * @param cmd 命令名，如 bold / italic / insertOrderedList / justifyCenter / removeFormat
 * @param arg 命令参数，insertHTML 等命令需要，普通格式命令可省略
 * 副作用：修改正文 DOM、触发 handleInput 回写 v-model、刷新工具栏激活态与选区缓存。
 */
function exec(cmd: string, arg?: string) {
  const editor = editorRef.value
  editor?.focus()
  // 工具栏已阻止 mousedown 抢焦点，编辑区内的选区通常仍有效；
  // 只有在选区丢失时才回退到上次保存的位置，避免用过期的 Range 覆盖当前选区
  const sel = window.getSelection()
  const hasEditorSelection = !!(sel && sel.rangeCount > 0 && editor && editor.contains(sel.anchorNode))
  if (!hasEditorSelection) restoreSelection()
  document.execCommand(cmd, false, arg)
  saveSelection()
  handleInput()
  updateActiveFormats()
}

/**
 * 插入图片：打开本地文件选择器，校验图片类型与 5MB 上限后上传，
 * 再把服务端返回的图片直链以 insertHTML 方式插入光标处。
 * 副作用：弹出系统文件框、发起上传请求、显示全局消息、修改正文并回写 v-model。
 * 注意：正文只保存 URL，文件本体存放在后端附件存储（Docker 卷）。
 */
function insertImage() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/png,image/jpeg'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    if (file.size > 5 * 1024 * 1024) {
      ElMessage.warning('图片大小不能超过 5MB')
      return
    }
    saveSelection()
    const loading = ElMessage({ message: '图片上传中…', duration: 0, type: 'info' })
    try {
      const res: any = await uploadFiles(file, 'editor', 0)
      const url = res?.data?.image_url
      if (!url) throw new Error('图片地址为空')
      editorRef.value?.focus()
      restoreSelection()
      const alt = file.name.replace(/["<>]/g, '')
      document.execCommand(
        'insertHTML', false,
        `<img src="${url}" alt="${alt}" style="max-width:100%;">`
      )
      saveSelection()
      handleInput()
      updateActiveFormats()
      ElMessage.success('图片已插入')
    } catch (_) {
      ElMessage.error('图片上传失败，请重试')
    } finally {
      loading.close()
    }
  }
  input.click()
}

// ==================== 输入与同步 ====================
/**
 * 正文 input 事件的统一出口：缓存选区并把 innerHTML 同步给父组件。
 * 若本次变化由组件内部回填 props 引起，则直接返回，避免重复 emit。
 * 副作用：可能向外触发 update:modelValue。
 */
function handleInput() {
  if (isInternalSet) return
  saveSelection()
  const html = editorRef.value?.innerHTML || ''
  emit('update:modelValue', html)
}

/**
 * 粘贴拦截：阻止浏览器默认粘贴，只取纯文本插入。
 * 目的：避免外部网页样式污染项目书排版，同时减少富文本携带脚本的风险。
 * 副作用：修改正文 DOM 并回写 v-model。
 */
function handlePaste(e: ClipboardEvent) {
  e.preventDefault()
  const text = e.clipboardData?.getData('text/plain') || ''
  editorRef.value?.focus()
  restoreSelection()
  document.execCommand('insertText', false, text)
  saveSelection()
  handleInput()
}

/**
 * 读取光标位置的格式状态，刷新工具栏按钮的高亮。
 * 副作用：更新 activeFormats，并顺带缓存当前选区。
 */
function updateActiveFormats() {
  saveSelection()
  try {
    activeFormats.value = {
      bold: document.queryCommandState('bold'),
      italic: document.queryCommandState('italic'),
      underline: document.queryCommandState('underline'),
      strikeThrough: document.queryCommandState('strikeThrough'),
    }
  } catch (_) {}
}

// ==================== 生命周期与外部同步 ====================
/** 组件更新前先保存选区，避免父组件重渲染导致光标位置丢失 */
onBeforeUpdate(() => {
  saveSelection()
})

/**
 * 监听外部 v-model 变化并回填正文。
 * 只有 DOM 内容与目标值不一致时才写入，防止与用户输入形成回环；
 * immediate 保证首次绑定也能初始化内容。
 */
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

/** 挂载后兜底写入初始值（与 watch immediate 互为保障，nextTick 确保 DOM 已就绪） */
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
/* 外框：工具栏与正文共用一个边框，聚焦时整体高亮为主色 */
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

/* 工具栏：可换行排列，窄屏时按钮自动折到下一行 */
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

/* 正文区：contenteditable 自带焦点轮廓需去掉，行高放宽以贴近公文阅读习惯 */
.editor-content {
  padding: 12px;
  line-height: 1.7;
  color: #303133;
  outline: none;
  word-break: break-word;
}

/* 占位符：仅在正文完全为空时渲染 data-placeholder，不参与实际内容与取值 */
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
