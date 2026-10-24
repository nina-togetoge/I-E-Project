<!--
  ==== AvatarCropper ====
  职责：头像裁剪弹窗。选择本地图片后在画布中拖动方形裁剪框、拖拽四角缩放，
        确认后输出 256x256、JPEG 质量 0.8 的 base64 dataURL。
  复用：个人中心 / 用户资料编辑中更换头像，同时支持鼠标与触摸（移动端）。
  契约：props：visible（配合 v-model:visible 控制显隐）；
        emits：update:visible（显隐同步）、success(dataUrl)（裁剪结果，父组件自行上传换取头像地址）；
        无插槽。
  注意：1) 组件只产出 base64，不负责上传，上传与保存由父组件调用用户接口完成；
        2) 裁剪框恒为正方形，最小 40px，且始终限制在图片显示区域内；
        3) 图片按容器等比缩放并居中，裁剪坐标需按缩放比例换算回原图；
        4) 弹窗 closed 时自动清空已选图片，避免下次打开残留上次的图。
-->
<template>
  <!-- 区块：裁剪弹窗，关闭动画结束后重置图片；禁止点击遮罩关闭，防止误丢裁剪进度 -->
  <el-dialog
    center
    :model-value="visible"
    @update:model-value="(v: boolean) => $emit('update:visible', v)"
    title="裁剪头像"
    width="520px"
    :close-on-click-modal="false"
    @closed="resetImage"
  >
    <div class="cropper-container">
      <!-- 区块：选择图片区（尚未选图时展示），点击打开系统文件选择框 -->
      <div class="upload-area" v-if="!imageSrc" @click="triggerFile">
        <el-icon :size="48" color="#909399"><Plus /></el-icon>
        <p>点击选择图片</p>
        <input
          ref="fileInput"
          type="file"
          accept="image/*"
          style="display: none"
          @change="handleFileChange"
        />
      </div>

      <!-- 区块：预览与裁剪区，黑色背景内等比居中展示图片，上层覆盖可拖拽的方形裁剪框 -->
      <div class="preview-area" v-else>
        <div class="canvas-wrapper" ref="canvasWrapper">
          <img
            ref="imgRef"
            :src="imageSrc"
            class="preview-img"
            @load="onImageLoad"
            draggable="false"
          />
          <!-- 裁剪框：本体负责移动，三等分网格线仅作视觉参考，四角负责等比缩放 -->
          <div
            class="crop-box"
            ref="cropBoxRef"
            @mousedown.stop="onCropMouseDown"
            @touchstart.stop.prevent="onCropTouchStart"
          >
            <div class="grid-line horizontal"></div>
            <div class="grid-line horizontal middle"></div>
            <div class="grid-line vertical"></div>
            <div class="grid-line vertical middle"></div>
            <div class="corner top-left" @mousedown.stop="onCornerMouseDown($event, 'tl')" @touchstart.stop.prevent="onCornerTouchStart($event, 'tl')"></div>
            <div class="corner top-right" @mousedown.stop="onCornerMouseDown($event, 'tr')" @touchstart.stop.prevent="onCornerTouchStart($event, 'tr')"></div>
            <div class="corner bottom-left" @mousedown.stop="onCornerMouseDown($event, 'bl')" @touchstart.stop.prevent="onCornerTouchStart($event, 'bl')"></div>
            <div class="corner bottom-right" @mousedown.stop="onCornerMouseDown($event, 'br')" @touchstart.stop.prevent="onCornerTouchStart($event, 'br')"></div>
          </div>
        </div>
      </div>

      <!-- 区块：裁剪操作提示与重新选择入口 -->
      <div class="actions-row" v-if="imageSrc">
        <el-button size="small" @click="resetImage">重新选择</el-button>
        <span class="tip">拖动方框移动位置，拖动四角调整大小</span>
      </div>
    </div>
    <!-- 区块：底部按钮，未选图时禁用"确定" -->
    <template #footer>
      <el-button @click="$emit('update:visible', false)">取消</el-button>
      <el-button type="primary" :disabled="!imageSrc" @click="handleCrop">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, nextTick, onBeforeUnmount } from 'vue'
import { Plus } from '@element-plus/icons-vue'

// ==================== props / emits ====================
/** 显隐控制，配合 v-model:visible 使用。 */
const props = withDefaults(
  defineProps<{
    /** 弹窗是否可见，默认 false */
    visible: boolean
  }>(),
  { visible: false }
)

/**
 * 对外事件：
 * - update:visible：显隐同步（取消、确定、右上角关闭都会触发）；
 * - success：裁剪完成，载荷为 256x256 JPEG base64 dataURL，父组件需自行上传并保存头像。
 */
const emit = defineEmits<{
  'update:visible': [v: boolean]
  success: [dataUrl: string]
}>()

// ==================== 状态 ====================
/** 隐藏的文件输入框引用，由"点击选择图片"代理触发 */
const fileInput = ref<HTMLInputElement>()
/** 预览图片元素引用，用于读取 naturalWidth/Height 并作为裁剪源 */
const imgRef = ref<HTMLImageElement>()
/** 裁剪画布容器引用，图片在其内部等比缩放居中 */
const canvasWrapper = ref<HTMLDivElement>()
/** 裁剪框 DOM 引用，尺寸位置通过 style 直接写入，避免每次拖动都触发重渲染 */
const cropBoxRef = ref<HTMLDivElement>()
/** 已选图片的 dataURL；为空表示尚未选图，展示上传区 */
const imageSrc = ref('')

// 裁剪框状态（单位 px，相对裁剪画布容器）
const crop = ref({ left: 0, top: 0, size: 100 })
// 图片在容器中的实际显示区域（缩放居中后的 left/top/width/height）
const imgRect = ref({ left: 0, top: 0, width: 0, height: 0 })
// 容器尺寸缓存（当前仅记录，用于调试与后续扩展）
const wrapperRect = ref({ width: 0, height: 0 })

// 拖动状态：move 移动裁剪框 / resize 四角缩放；null 表示未拖动
let dragMode: 'move' | 'resize' | null = null
// 当前拖动的角：tl 左上 / tr 右上 / bl 左下 / br 右下
let dragCorner: string = ''
// 按下时的鼠标/触摸坐标与裁剪框初始状态，用于计算位移增量
let startX = 0
let startY = 0
let startCrop = { left: 0, top: 0, size: 0 }

// ==================== 选择与重置 ====================
/**
 * 触发隐藏的文件输入框，打开系统文件选择器。
 * 副作用：唤起系统文件选择框。
 */
function triggerFile() {
  fileInput.value?.click()
}

/**
 * 选择文件后读取为 dataURL 并进入裁剪态。
 * @param e input 的 change 事件
 * 副作用：文件非图片时静默忽略；读取成功后写入 imageSrc，图片 load 后触发 onImageLoad。
 * 说明：用 FileReader 而非 ObjectURL，便于直接作为 canvas 绘制源且无需手动释放。
 */
function handleFileChange(e: Event) {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  if (!file.type.startsWith('image/')) return
  const reader = new FileReader()
  reader.onload = (ev) => {
    imageSrc.value = ev.target?.result as string
  }
  reader.readAsDataURL(file)
}

/**
 * 重置到选图初始态：清空预览与文件输入框的值。
 * 副作用：修改 imageSrc 与原生 input.value；否则重复选择同一文件不会触发 change。
 */
function resetImage() {
  imageSrc.value = ''
  if (fileInput.value) fileInput.value.value = ''
}

/**
 * 图片加载完成后计算等比居中布局并初始化裁剪框。
 * 副作用：直接修改 img 元素的 width/height/left/top 与 cropBox 样式，写入 imgRect / wrapperRect / crop。
 * 说明：裁剪框默认居中，边长为图片短边的 75%，给用户留出可拖动余量。
 */
function onImageLoad() {
  nextTick(() => {
    const wrapper = canvasWrapper.value
    const img = imgRef.value
    const cropBox = cropBoxRef.value
    if (!wrapper || !img || !cropBox) return

    const ww = wrapper.clientWidth
    const wh = wrapper.clientHeight
    wrapperRect.value = { width: ww, height: wh }

    const iw = img.naturalWidth
    const ih = img.naturalHeight
    const scale = Math.min(ww / iw, wh / ih)
    const dispW = iw * scale
    const dispH = ih * scale
    const dispLeft = (ww - dispW) / 2
    const dispTop = (wh - dispH) / 2

    img.style.width = dispW + 'px'
    img.style.height = dispH + 'px'
    img.style.left = dispLeft + 'px'
    img.style.top = dispTop + 'px'

    imgRect.value = { left: dispLeft, top: dispTop, width: dispW, height: dispH }

    // 初始化裁剪框：居中，边长为图片短边的 75%
    const size = Math.min(dispW, dispH) * 0.75
    crop.value = {
      left: dispLeft + (dispW - size) / 2,
      top: dispTop + (dispH - size) / 2,
      size,
    }
    applyCropStyle()
  })
}

/**
 * 把裁剪框状态同步到 DOM 内联样式。
 * 副作用：直接写入裁剪框的 left/top/width/height。
 * 说明：绕过响应式绑定以降低拖动过程的渲染开销。
 */
function applyCropStyle() {
  const cropBox = cropBoxRef.value
  if (!cropBox) return
  cropBox.style.left = crop.value.left + 'px'
  cropBox.style.top = crop.value.top + 'px'
  cropBox.style.width = crop.value.size + 'px'
  cropBox.style.height = crop.value.size + 'px'
}

/**
 * 数值夹取到 [min, max] 区间。
 * @param val 原始值
 * @param min 下界
 * @param max 上界
 * @returns 夹取后的值，用于防止裁剪框越出图片区域
 */
function clamp(val: number, min: number, max: number) {
  return Math.max(min, Math.min(max, val))
}

// ==================== 拖动裁剪框（鼠标 / 触摸） ====================
/**
 * 裁剪框按下（鼠标）：进入移动模式并记录起点。
 * @param e 鼠标按下事件
 * 副作用：修改拖动状态，向 document 注册 mousemove / mouseup。
 */
function onCropMouseDown(e: MouseEvent) {
  dragMode = 'move'
  startX = e.clientX
  startY = e.clientY
  startCrop = { ...crop.value }
  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
}

/**
 * 裁剪框按下（触摸）：与鼠标逻辑一致，取第一个触点作为起点。
 * @param e 触摸开始事件
 * 副作用：修改拖动状态，向 document 注册 touchmove（passive:false 以便 preventDefault）。
 */
function onCropTouchStart(e: TouchEvent) {
  dragMode = 'move'
  const t = e.touches[0]
  startX = t.clientX
  startY = t.clientY
  startCrop = { ...crop.value }
  document.addEventListener('touchmove', onTouchMove, { passive: false })
  document.addEventListener('touchend', onTouchEnd)
}

// ===== 四角缩放 =====
/**
 * 四角按下（鼠标）：进入缩放模式并记录是哪个角。
 * @param e 鼠标按下事件
 * @param corner 角标识：tl / tr / bl / br
 * 副作用：修改拖动状态，向 document 注册 mousemove / mouseup。
 */
function onCornerMouseDown(e: MouseEvent, corner: string) {
  dragMode = 'resize'
  dragCorner = corner
  startX = e.clientX
  startY = e.clientY
  startCrop = { ...crop.value }
  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
}

/**
 * 四角按下（触摸）：与鼠标缩放逻辑一致。
 * @param e 触摸开始事件
 * @param corner 角标识：tl / tr / bl / br
 * 副作用：修改拖动状态，向 document 注册 touchmove / touchend。
 */
function onCornerTouchStart(e: TouchEvent, corner: string) {
  dragMode = 'resize'
  dragCorner = corner
  const t = e.touches[0]
  startX = t.clientX
  startY = t.clientY
  startCrop = { ...crop.value }
  document.addEventListener('touchmove', onTouchMove, { passive: false })
  document.addEventListener('touchend', onTouchEnd)
}

/**
 * 鼠标移动：把坐标交给统一的位移计算函数。
 * @param e 鼠标移动事件
 */
function onMouseMove(e: MouseEvent) {
  handleMove(e.clientX, e.clientY)
}

/**
 * 触摸移动：阻止页面滚动后按第一个触点更新裁剪框。
 * @param e 触摸移动事件
 * 副作用：调用 preventDefault，避免移动端拖动裁剪框时页面跟着滚动。
 */
function onTouchMove(e: TouchEvent) {
  e.preventDefault()
  const t = e.touches[0]
  handleMove(t.clientX, t.clientY)
}

/**
 * 统一的拖动/缩放计算入口。
 * @param clientX 当前指针横坐标
 * @param clientY 当前指针纵坐标
 * 副作用：更新 crop 状态并同步裁剪框样式。
 * 规则：移动模式限制裁剪框完全落在图片显示区域内；
 *       缩放模式始终保持正方形，最小 40px，且按拖动的角决定左/上边界是否跟随移动。
 */
function handleMove(clientX: number, clientY: number) {
  if (!dragMode) return
  const dx = clientX - startX
  const dy = clientY - startY
  const ir = imgRect.value

  if (dragMode === 'move') {
    let newLeft = startCrop.left + dx
    let newTop = startCrop.top + dy
    // 限制在图片范围内
    newLeft = clamp(newLeft, ir.left, ir.left + ir.width - crop.value.size)
    newTop = clamp(newTop, ir.top, ir.top + ir.height - crop.value.size)
    crop.value.left = newLeft
    crop.value.top = newTop
  } else if (dragMode === 'resize') {
    let newSize = startCrop.size
    let newLeft = startCrop.left
    let newTop = startCrop.top

    // 根据角计算新尺寸（保持正方形）
    if (dragCorner === 'br') {
      newSize = Math.max(40, startCrop.size + Math.max(dx, dy))
    } else if (dragCorner === 'tl') {
      newSize = Math.max(40, startCrop.size - Math.min(dx, dy))
      newLeft = startCrop.left + (startCrop.size - newSize)
      newTop = startCrop.top + (startCrop.size - newSize)
    } else if (dragCorner === 'tr') {
      newSize = Math.max(40, startCrop.size + Math.max(dx, -dy))
      newTop = startCrop.top + (startCrop.size - newSize)
    } else if (dragCorner === 'bl') {
      newSize = Math.max(40, startCrop.size + Math.max(-dx, dy))
      newLeft = startCrop.left + (startCrop.size - newSize)
    }

    // 限制不超出图片范围
    const maxSizeByRight = ir.left + ir.width - newLeft
    const maxSizeByBottom = ir.top + ir.height - newTop
    const maxSizeByLeft = newLeft + newSize - ir.left
    const maxSizeByTop = newTop + newSize - ir.top
    const maxSize = Math.min(maxSizeByRight, maxSizeByBottom, ir.width, ir.height)
    newSize = Math.min(newSize, maxSize)
    if (newSize < 40) newSize = 40

    // 再校正位置确保不越界
    newLeft = clamp(newLeft, ir.left, ir.left + ir.width - newSize)
    newTop = clamp(newTop, ir.top, ir.top + ir.height - newSize)

    crop.value = { left: newLeft, top: newTop, size: newSize }
  }

  applyCropStyle()
}

/**
 * 鼠标抬起：结束拖动并注销 document 监听。
 * 副作用：重置 dragMode，移除 mousemove / mouseup。
 */
function onMouseUp() {
  dragMode = null
  document.removeEventListener('mousemove', onMouseMove)
  document.removeEventListener('mouseup', onMouseUp)
}

/**
 * 触摸结束：结束拖动并注销 document 监听。
 * 副作用：重置 dragMode，移除 touchmove / touchend。
 */
function onTouchEnd() {
  dragMode = null
  document.removeEventListener('touchmove', onTouchMove)
  document.removeEventListener('touchend', onTouchEnd)
}

// ==================== 生命周期 ====================
/**
 * 卸载时兜底移除四类 document 监听，
 * 覆盖"拖动中弹窗被销毁"的场景，防止监听残留与内存泄漏。
 */
onBeforeUnmount(() => {
  document.removeEventListener('mousemove', onMouseMove)
  document.removeEventListener('mouseup', onMouseUp)
  document.removeEventListener('touchmove', onTouchMove)
  document.removeEventListener('touchend', onTouchEnd)
})

// ==================== 导出裁剪结果 ====================
/**
 * 按裁剪框位置从原图截取正方形并压缩为 JPEG base64。
 * 换算：裁剪坐标除以图片显示宽度得到缩放比，再乘以原图 naturalWidth 得到源图采样区域。
 * 副作用：创建离屏 canvas、绘制并编码，向外触发 success 与 update:visible（关闭弹窗）。
 * 输出：256x256、quality=0.8，控制 base64 体积便于直接上传。
 */
function handleCrop() {
  const wrapper = canvasWrapper.value
  const img = imgRef.value
  if (!wrapper || !img) return

  const ir = imgRect.value
  const iw = img.naturalWidth
  const scale = iw / ir.width

  // 裁剪框相对于图片的位置
  const sx = (crop.value.left - ir.left) * scale
  const sy = (crop.value.top - ir.top) * scale
  const sw = crop.value.size * scale
  const sh = crop.value.size * scale

  // 输出 256x256，质量 0.8，控制 base64 体积
  const OUTPUT_SIZE = 256
  const canvas = document.createElement('canvas')
  canvas.width = OUTPUT_SIZE
  canvas.height = OUTPUT_SIZE
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.drawImage(img, sx, sy, sw, sh, 0, 0, OUTPUT_SIZE, OUTPUT_SIZE)
  const dataUrl = canvas.toDataURL('image/jpeg', 0.8)
  emit('success', dataUrl)
  emit('update:visible', false)
}
</script>

<style scoped>
.cropper-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.upload-area {
  width: 100%;
  height: 360px;
  border: 2px dashed #dcdfe6;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: #909399;
  transition: border-color 0.2s;
}
.upload-area:hover {
  border-color: var(--el-color-primary, #409EFF);
  color: var(--el-color-primary, #409EFF);
}
.upload-area p {
  margin-top: 12px;
  font-size: 14px;
}

.preview-area {
  width: 100%;
}

.canvas-wrapper {
  position: relative;
  width: 100%;
  height: 360px;
  background: #000;
  border-radius: 8px;
  overflow: hidden;
}

.preview-img {
  position: absolute;
  user-select: none;
  -webkit-user-drag: none;
}

.crop-box {
  position: absolute;
  border: 1.5px solid #fff;
  box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.5);
  cursor: move;
}

.grid-line {
  position: absolute;
  background: rgba(255, 255, 255, 0.5);
  pointer-events: none;
}
.grid-line.horizontal {
  left: 0; right: 0; height: 1px;
}
.grid-line.vertical {
  top: 0; bottom: 0; width: 1px;
}
.grid-line.horizontal:nth-child(1) { top: 33.33%; }
.grid-line.horizontal:nth-child(2) { top: 66.66%; }
.grid-line.vertical:nth-child(3) { left: 33.33%; }
.grid-line.vertical:nth-child(4) { left: 66.66%; }

.corner {
  position: absolute;
  width: 12px;
  height: 12px;
  background: var(--el-color-primary, #409EFF);
  border: 2px solid #fff;
  border-radius: 2px;
  z-index: 2;
}
.corner.top-left {
  top: -7px; left: -7px;
  cursor: nwse-resize;
}
.corner.top-right {
  top: -7px; right: -7px;
  cursor: nesw-resize;
}
.corner.bottom-left {
  bottom: -7px; left: -7px;
  cursor: nesw-resize;
}
.corner.bottom-right {
  bottom: -7px; right: -7px;
  cursor: nwse-resize;
}

.actions-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 16px;
}
.tip {
  font-size: 12px;
  color: #909399;
}
</style>
