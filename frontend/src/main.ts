/**
 * ==== 应用入口 main.ts ====
 * 职责：创建 Vue 应用实例，按固定顺序完成全局插件、样式、指令与根组件挂载。
 * 被谁引用：index.html 通过 /src/main.ts 加载；生产构建由 Vite 作为入口。
 * 注册顺序与原因：
 *   1. 先注册 Element Plus 图标组件，保证模板中按名称使用图标时已存在；
 *   2. 再注册自定义指令 ripple / lazy；
 *   3. 然后 use(Pinia) → use(Router) → use(ElementPlus)：
 *      Pinia 必须先于 Router，因为路由守卫内部会使用 store；
 *      Element Plus 最后注册，并通过 zIndex 抬高全局弹层层级。
 * 关键约定：全局样式只在此处引入一次（index.css 基础样式 + themes.css 主题变量）；
 *          生产环境保留一段历史 Service Worker 自清理逻辑，避免旧缓存残留。
 */
import { createApp, type Directive } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import zhCn from 'element-plus/es/locale/lang/zh-cn'

// 根组件与路由：router 内部已包含鉴权守卫，必须在 Pinia 之后注册
import App from './App.vue'
import router from './router'
// 全局样式：index.css 放基础重置与通用类，themes.css 放明暗主题变量
import './styles/index.css'
import './styles/themes.css'

// ==================== 应用实例 ====================
const app = createApp(App)

// ==================== 全局图标注册 ====================
// 全量注册 Element Plus 图标为全局组件，模板可直接写 <HomeFilled /> 或动态 :is="'User'"。
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

// ==================== 自定义指令：v-ripple ====================
// 点击时在元素内动态插入一个圆形波纹，650ms 后移除；纯视觉反馈，不影响业务事件。
const rippleDirective: Directive<HTMLElement> = {
  mounted(el) {
    el.addEventListener('click', (e: MouseEvent) => {
      // 以元素长边作为波纹直径，并按点击坐标定位到圆心
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

      // 动画结束后移除节点，避免大量点击后 DOM 节点堆积
      window.setTimeout(() => {
        ripple.remove()
      }, 650)
    })
  },
}

// 注册为全局指令后，任意组件可写 v-ripple
app.directive('ripple', rippleDirective)

// ==================== 自定义指令：v-lazy ====================
// 图片加载失败时的兜底 SVG（data URI），避免出现浏览器默认的破图图标。
const BROKEN_IMG_SVG =
  'data:image/svg+xml;charset=UTF-8,' +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect fill="#f5f7fa" width="100" height="100"/><text x="50%" y="50%" font-family="Arial" font-size="12" fill="#909399" text-anchor="middle" dominant-baseline="middle">图片加载失败</text></svg>`
  )

// 图片懒加载：使用 IntersectionObserver 在距视口 100px 时赋值真实 src；
// 不支持该 API 的浏览器直接加载；加载失败统一切换到兜底 SVG。
const lazyDirective: Directive<HTMLImageElement, string> = {
  mounted(el, binding) {
    el.classList.add('img-lazy-placeholder')
    el.style.minHeight = '80px'

    const realSrc = binding.value

    // 兼容分支：浏览器不支持 IntersectionObserver 时退化为立即加载
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
  // 绑定值变化时重新进入占位并替换 src；已观察元素无需重新 observe
  updated(el, binding) {
    if (binding.oldValue !== binding.value) {
      el.classList.add('img-lazy-placeholder')
      el.src = binding.value
    }
  },
}

app.directive('lazy', lazyDirective)

// ==================== 插件注册顺序 ====================
// Pinia 必须先于 Router 注册：路由守卫中会调用 useUserStore，需保证 store 已可用。
app.use(createPinia())
app.use(router)
// zIndex 起始值高于项目内自定义悬浮窗的固定层级（3000/4000），
// 确保 Element 的弹窗、下拉、气泡等提示层始终显示在弹窗之上。
// Element Plus 使用中文语言包，确保分页、日期选择、消息提示等文案为中文。
app.use(ElementPlus, { locale: zhCn, zIndex: 5000 })

// ==================== 历史 Service Worker 清理 ====================
// Service Worker 已移除（登录型管理系统无离线需求，且缓存策略导致发版后旧页面残留）。
// 以下为存量浏览器的一次性自清理：注销历史 SW 并清空其缓存，之后可整体删除。
// 仅在生产环境执行，避免影响开发期热更新。
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  navigator.serviceWorker.getRegistrations().then((regs) => {
    regs.forEach((r) => r.unregister())
  }).catch(() => {})
  if ('caches' in window) {
    caches.keys().then((keys) => keys.forEach((k) => caches.delete(k))).catch(() => {})
  }
}

// ==================== 挂载 ====================
// 挂载到 index.html 的 #app 节点；此后 App.vue 内部接管路由渲染与全局错误边界。
app.mount('#app')
