import { createApp, type Directive } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import zhCn from 'element-plus/es/locale/lang/zh-cn'

import App from './App.vue'
import router from './router'
import './styles/index.css'
import './styles/themes.css'

const app = createApp(App)

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

const rippleDirective: Directive<HTMLElement> = {
  mounted(el) {
    el.addEventListener('click', (e: MouseEvent) => {
      const rect = el.getBoundingClientRect()
      const ripple = document.createElement('span')
      const size = Math.max(rect.width, rect.height)
      const x = e.clientX - rect.left - size / 2
      const y = e.clientY - rect.top - size / 2

      ripple.style.width = ripple.style.height = size + 'px'
      ripple.style.left = x + 'px'
      ripple.style.top = y + 'px'
      ripple.classList.add('ripple')

      el.appendChild(ripple)

      window.setTimeout(() => {
        ripple.remove()
      }, 650)
    })
  },
}

app.directive('ripple', rippleDirective)

const BROKEN_IMG_SVG =
  'data:image/svg+xml;charset=UTF-8,' +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect fill="#f5f7fa" width="100" height="100"/><text x="50%" y="50%" font-family="Arial" font-size="12" fill="#909399" text-anchor="middle" dominant-baseline="middle">图片加载失败</text></svg>`
  )

const lazyDirective: Directive<HTMLImageElement, string> = {
  mounted(el, binding) {
    el.classList.add('img-lazy-placeholder')
    el.style.minHeight = '80px'

    const realSrc = binding.value

    if (!('IntersectionObserver' in window)) {
      el.src = realSrc
      el.addEventListener('load', () => el.classList.remove('img-lazy-placeholder'))
      el.addEventListener('error', () => {
        el.src = BROKEN_IMG_SVG
        el.classList.remove('img-lazy-placeholder')
      })
      return
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            el.src = realSrc
            el.addEventListener('load', () => el.classList.remove('img-lazy-placeholder'))
            el.addEventListener('error', () => {
              el.src = BROKEN_IMG_SVG
              el.classList.remove('img-lazy-placeholder')
            })
            observer.unobserve(el)
          }
        })
      },
      { rootMargin: '100px' }
    )

    observer.observe(el)
  },
  updated(el, binding) {
    if (binding.oldValue !== binding.value) {
      el.classList.add('img-lazy-placeholder')
      el.src = binding.value
    }
  },
}

app.directive('lazy', lazyDirective)

app.use(createPinia())
app.use(router)
// zIndex 起始值高于项目内自定义悬浮窗的固定层级（3000/4000），
// 确保 Element 的弹窗、下拉、气泡等提示层始终显示在弹窗之上。
app.use(ElementPlus, { locale: zhCn, zIndex: 5000 })

// Service Worker 已移除（登录型管理系统无离线需求，且缓存策略导致发版后旧页面残留）。
// 以下为存量浏览器的一次性自清理：注销历史 SW 并清空其缓存，之后可整体删除。
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  navigator.serviceWorker.getRegistrations().then((regs) => {
    regs.forEach((r) => r.unregister())
  }).catch(() => {})
  if ('caches' in window) {
    caches.keys().then((keys) => keys.forEach((k) => caches.delete(k))).catch(() => {})
  }
}

app.mount('#app')
