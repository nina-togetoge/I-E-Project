<template>
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

      <div class="preview-area" v-else>
        <div class="canvas-wrapper" ref="canvasWrapper">
          <img
            ref="imgRef"
            :src="imageSrc"
            class="preview-img"
            @load="onImageLoad"
            draggable="false"
          />
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

      <div class="actions-row" v-if="imageSrc">
        <el-button size="small" @click="resetImage">重新选择</el-button>
        <span class="tip">拖动方框移动位置，拖动四角调整大小</span>
      </div>
    </div>
    <template #footer>
      <el-button @click="$emit('update:visible', false)">取消</el-button>
      <el-button type="primary" :disabled="!imageSrc" @click="handleCrop">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, nextTick, onBeforeUnmount } from 'vue'
import { Plus } from '@element-plus/icons-vue'

const props = withDefaults(
  defineProps<{
    visible: boolean
  }>(),
  { visible: false }
)

const emit = defineEmits<{
  'update:visible': [v: boolean]
  success: [dataUrl: string]
}>()

const fileInput = ref<HTMLInputElement>()
const imgRef = ref<HTMLImageElement>()
const canvasWrapper = ref<HTMLDivElement>()
const cropBoxRef = ref<HTMLDivElement>()
const imageSrc = ref('')

// 裁剪框状态
const crop = ref({ left: 0, top: 0, size: 100 })
// 图片显示区域
const imgRect = ref({ left: 0, top: 0, width: 0, height: 0 })
const wrapperRect = ref({ width: 0, height: 0 })

// 拖动状态
let dragMode: 'move' | 'resize' | null = null
let dragCorner: string = ''
let startX = 0
let startY = 0
let startCrop = { left: 0, top: 0, size: 0 }

function triggerFile() {
  fileInput.value?.click()
}

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

function resetImage() {
  imageSrc.value = ''
  if (fileInput.value) fileInput.value.value = ''
}

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

function applyCropStyle() {
  const cropBox = cropBoxRef.value
  if (!cropBox) return
  cropBox.style.left = crop.value.left + 'px'
  cropBox.style.top = crop.value.top + 'px'
  cropBox.style.width = crop.value.size + 'px'
  cropBox.style.height = crop.value.size + 'px'
}

function clamp(val: number, min: number, max: number) {
  return Math.max(min, Math.min(max, val))
}

// ===== 拖动裁剪框 =====
function onCropMouseDown(e: MouseEvent) {
  dragMode = 'move'
  startX = e.clientX
  startY = e.clientY
  startCrop = { ...crop.value }
  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
}

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
function onCornerMouseDown(e: MouseEvent, corner: string) {
  dragMode = 'resize'
  dragCorner = corner
  startX = e.clientX
  startY = e.clientY
  startCrop = { ...crop.value }
  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
}

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

function onMouseMove(e: MouseEvent) {
  handleMove(e.clientX, e.clientY)
}

function onTouchMove(e: TouchEvent) {
  e.preventDefault()
  const t = e.touches[0]
  handleMove(t.clientX, t.clientY)
}

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

function onMouseUp() {
  dragMode = null
  document.removeEventListener('mousemove', onMouseMove)
  document.removeEventListener('mouseup', onMouseUp)
}

function onTouchEnd() {
  dragMode = null
  document.removeEventListener('touchmove', onTouchMove)
  document.removeEventListener('touchend', onTouchEnd)
}

onBeforeUnmount(() => {
  document.removeEventListener('mousemove', onMouseMove)
  document.removeEventListener('mouseup', onMouseUp)
  document.removeEventListener('touchmove', onTouchMove)
  document.removeEventListener('touchend', onTouchEnd)
})

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
