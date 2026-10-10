<template>
  <div class="empty-illustration">
    <div class="illustration-svg">
      <svg-default v-if="type === 'default'" />
      <svg-search v-else-if="type === 'search'" />
      <svg-project v-else-if="type === 'project'" />
      <svg-file v-else-if="type === 'file'" />
      <svg-error v-else-if="type === 'error'" />
      <svg-default v-else />
    </div>
    <p class="empty-desc">
      <slot>{{ description || '暂无数据' }}</slot>
    </p>
  </div>
</template>

<script setup lang="ts">
import { h } from 'vue'

defineProps<{
  type?: 'default' | 'search' | 'project' | 'file' | 'error'
  description?: string
}>()

const strokeColor = 'var(--primary-color, #409EFF)'
const strokeGray = 'var(--text-color-secondary, #909399)'
const fillLight = 'rgba(64, 158, 255, 0.08)'

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

.empty-desc {
  font-size: 14px;
  color: var(--text-color-secondary, #909399);
  margin: 0;
  text-align: center;
  line-height: 1.6;
  max-width: 360px;
}
</style>
