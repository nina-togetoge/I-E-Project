<!--
  ==== EmptyIllustration ====
  职责：空状态 / 占位插画组件。用内联 SVG 提供 default / search / project / file / error 五种场景图，
        下方配一句说明文案。
  复用：表格空数据、搜索无结果、我的项目为空、附件缺失、页面异常等场景。
  契约：props：type（五种场景之一，默认 default）、description（说明文案，默认"暂无数据"）；
        插槽：默认插槽可完全替换文案区域。
  注意：1) SVG 全部内联绘制，无外部图片资源，离线与深色主题下也能正常展示；
        2) 颜色使用 CSS 变量并带兜底值，跟随全局主题色；
        3) 组件只做展示，不包含重试 / 刷新等交互，需要时由父组件包一层按钮。
-->
<template>
  <div class="empty-illustration">
    <!-- 区块：插画区域，按 type 选择对应 SVG，未知类型回落到 default -->
    <div class="illustration-svg">
      <svg-default v-if="type === 'default'" />
      <svg-search v-else-if="type === 'search'" />
      <svg-project v-else-if="type === 'project'" />
      <svg-file v-else-if="type === 'file'" />
      <svg-error v-else-if="type === 'error'" />
      <svg-default v-else />
    </div>
    <!-- 区块：说明文案。默认插槽优先，其次 description，最后兜底"暂无数据" -->
    <p class="empty-desc">
      <slot>{{ description || '暂无数据' }}</slot>
    </p>
  </div>
</template>

<script setup lang="ts">
import { h } from 'vue'

// ==================== props ====================
/**
 * 展示配置。
 * type 取值含义：default 通用空数据 / search 搜索无结果 / project 无项目 /
 *               file 无附件或文件缺失 / error 加载异常。
 */
defineProps<{
  /** 场景类型，默认 default；决定渲染哪一张 SVG */
  type?: 'default' | 'search' | 'project' | 'file' | 'error'
  /** 说明文案，默认"暂无数据"；优先级低于默认插槽 */
  description?: string
}>()

// ==================== 配色常量 ====================
/** 主题主色，用于插画中的强调元素，兜底为 Element Plus 默认蓝 */
const strokeColor = 'var(--primary-color, #409EFF)'
/** 次级文字色，用于线稿主体，兜底为灰色 */
const strokeGray = 'var(--text-color-secondary, #909399)'
/** 主色的低透明度填充，用于插画中的色块区域 */
const fillLight = 'rgba(64, 158, 255, 0.08)'

// ==================== 插画定义 ====================
/**
 * 通用空状态：虚线文档轮廓 + 一枚主色小方块，表达"内容待填充"。
 * 使用 render 函数而非模板，便于按 type 动态切换且无需额外子组件文件。
 */
const svgDefault = {
  render() {
    return h('svg', {
      width: '160',
      height: '160',
      viewBox: '0 0 160 160',
      fill: 'none',
      xmlns: 'http://www.w3.org/2000/svg',
    }, [
      h('rect', {
        x: '28', y: '36', width: '104', height: '88', rx: '8',
        stroke: strokeGray, 'stroke-width': '2', 'stroke-dasharray': '4 3',
      }),
      h('path', {
        d: 'M28 58 H132',
        stroke: strokeGray, 'stroke-width': '2', 'stroke-dasharray': '4 3',
      }),
      h('path', {
        d: 'M48 76 H78',
        stroke: strokeGray, 'stroke-width': '2', 'stroke-linecap': 'round',
      }),
      h('path', {
        d: 'M48 92 H110',
        stroke: strokeGray, 'stroke-width': '2', 'stroke-linecap': 'round',
      }),
      h('path', {
        d: 'M48 108 H92',
        stroke: strokeGray, 'stroke-width': '2', 'stroke-linecap': 'round',
      }),
      h('path', {
        d: 'M60 140 L52 148 L70 148 L60 140 Z M100 140 L92 148 L110 148 L100 140 Z',
        fill: strokeGray, opacity: '0.5',
      }),
      h('rect', {
        x: '50', y: '78', width: '14', height: '14', rx: '3',
        transform: 'rotate(12 57 85)',
        fill: strokeColor, opacity: '0.85',
      }),
    ])
  },
}

/** 搜索无结果：放大镜 + 内部淡色圆，用于列表筛选/关键词搜索返回空的场景 */
const svgSearch = {
  render() {
    return h('svg', {
      width: '160', height: '160', viewBox: '0 0 160 160',
      fill: 'none', xmlns: 'http://www.w3.org/2000/svg',
    }, [
      h('circle', {
        cx: '70', cy: '70', r: '40',
        stroke: strokeColor, 'stroke-width': '3',
      }),
      h('circle', {
        cx: '70', cy: '70', r: '28',
        fill: fillLight,
      }),
      h('path', {
        d: 'M100 100 L136 136',
        stroke: strokeColor, 'stroke-width': '5', 'stroke-linecap': 'round',
      }),
      h('circle', { cx: '70', cy: '70', r: '6', fill: strokeColor, opacity: '0.6' }),
      h('path', {
        d: 'M56 60 Q62 54 70 56 T84 62',
        stroke: strokeGray, 'stroke-width': '2', 'stroke-linecap': 'round', fill: 'none',
      }),
      h('path', {
        d: 'M56 78 Q62 74 70 76 T84 80',
        stroke: strokeGray, 'stroke-width': '2', 'stroke-linecap': 'round', fill: 'none', opacity: '0.6',
      }),
    ])
  },
}

/** 无项目：文件夹 + 加号徽标，用于「我的项目」「项目库」等列表为空 */
const svgProject = {
  render() {
    return h('svg', {
      width: '160', height: '160', viewBox: '0 0 160 160',
      fill: 'none', xmlns: 'http://www.w3.org/2000/svg',
    }, [
      h('path', {
        d: 'M36 44 H74 L86 32 H128 V120 H36 Z',
        stroke: strokeColor, 'stroke-width': '2.5', fill: fillLight,
      }),
      h('path', {
        d: 'M74 44 V32 H86',
        stroke: strokeColor, 'stroke-width': '2.5', fill: 'none',
      }),
      h('path', {
        d: 'M54 70 H108',
        stroke: strokeColor, 'stroke-width': '2.5', 'stroke-linecap': 'round',
      }),
      h('path', {
        d: 'M54 88 H96',
        stroke: strokeGray, 'stroke-width': '2', 'stroke-linecap': 'round',
      }),
      h('path', {
        d: 'M54 104 H86',
        stroke: strokeGray, 'stroke-width': '2', 'stroke-linecap': 'round',
      }),
      h('circle', {
        cx: '108', cy: '92', r: '14',
        fill: 'none', stroke: strokeColor, 'stroke-width': '2',
        'stroke-dasharray': '3 3', opacity: '0.7',
      }),
      h('path', {
        d: 'M108 84 V100 M100 92 H116',
        stroke: strokeColor, 'stroke-width': '2.5', 'stroke-linecap': 'round',
      }),
    ])
  },
}

/** 无附件：带折角的文件 + 表格线，用于材料/佐证附件缺失提示 */
const svgFile = {
  render() {
    return h('svg', {
      width: '160', height: '160', viewBox: '0 0 160 160',
      fill: 'none', xmlns: 'http://www.w3.org/2000/svg',
    }, [
      h('path', {
        d: 'M46 128 V30 H100 L126 56 V128 Z',
        stroke: strokeColor, 'stroke-width': '2.5', fill: fillLight,
      }),
      h('path', {
        d: 'M100 30 V56 H126',
        stroke: strokeColor, 'stroke-width': '2.5', fill: 'none',
      }),
      h('path', {
        d: 'M46 82 H126',
        stroke: strokeColor, 'stroke-width': '2', opacity: '0.4',
      }),
      h('rect', {
        x: '60', y: '62', width: '40', height: '28', rx: '3',
        stroke: strokeGray, 'stroke-width': '2',
        fill: '#fff',
      }),
      h('path', {
        d: 'M68 72 H92 M68 80 H86',
        stroke: strokeGray, 'stroke-width': '2', 'stroke-linecap': 'round',
      }),
      h('path', {
        d: 'M66 100 H106 M66 110 H98',
        stroke: strokeGray, 'stroke-width': '2', 'stroke-linecap': 'round', opacity: '0.7',
      }),
    ])
  },
}

/** 异常/失败：云朵 + 沮丧表情（嘴角用错误红），用于接口失败或页面加载异常 */
const svgError = {
  render() {
    return h('svg', {
      width: '160', height: '160', viewBox: '0 0 160 160',
      fill: 'none', xmlns: 'http://www.w3.org/2000/svg',
    }, [
      h('path', {
        d: 'M28 104 Q28 72 56 70 Q64 50 80 50 Q98 50 104 70 Q132 72 132 104 V108 H28 Z',
        stroke: strokeColor, 'stroke-width': '2.5', fill: fillLight,
      }),
      h('path', {
        d: 'M80 28 L80 50',
        stroke: strokeColor, 'stroke-width': '2.5', 'stroke-linecap': 'round',
      }),
      h('path', {
        d: 'M72 36 H88',
        stroke: strokeColor, 'stroke-width': '2.5', 'stroke-linecap': 'round',
      }),
      h('circle', {
        cx: '64', cy: '90', r: '5', fill: strokeColor,
      }),
      h('circle', {
        cx: '96', cy: '90', r: '5', fill: strokeColor,
      }),
      h('path', {
        d: 'M64 112 Q72 104 80 112 T96 112',
        stroke: '#F56C6C', 'stroke-width': '2.5', 'stroke-linecap': 'round', fill: 'none',
      }),
      h('path', {
        d: 'M60 82 L68 90',
        stroke: strokeColor, 'stroke-width': '2', 'stroke-linecap': 'round',
      }),
      h('path', {
        d: 'M92 90 L100 82',
        stroke: strokeColor, 'stroke-width': '2', 'stroke-linecap': 'round',
      }),
    ])
  },
}
</script>

<style scoped>
/* 容器：垂直居中排布，插画与文案之间由 .illustration-svg 的下边距隔开 */
.empty-illustration {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  user-select: none;
}

.illustration-svg {
  margin-bottom: 16px;
  opacity: 0.95;
}

/* 文案：限制最大宽度，长说明自动换行并保持居中 */
.empty-desc {
  font-size: 14px;
  color: var(--text-color-secondary, #909399);
  margin: 0;
  text-align: center;
  line-height: 1.6;
  max-width: 360px;
}
</style>
