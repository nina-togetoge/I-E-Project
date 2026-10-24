/**
 * ==== 前端类型声明 env.d.ts ====
 * 职责：补充 Vite 与 .vue 文件的 TypeScript 类型，使 vue-tsc 能正确解析 SFC 导入与环境变量。
 * 被谁引用：tsconfig 的 include 范围自动纳入，无需显式 import。
 * 关键约定：ImportMetaEnv 的字段需与 .env 文件、Vite 的 VITE_ 前缀变量保持一致，
 *          新增环境变量时同步在此声明，否则 import.meta.env 读取会报类型错误。
 */

// ==================== Vite 客户端类型 ====================
/// <reference types="vite/client" />

// ==================== .vue 单文件组件声明 ====================
// 让 TS 将 import Xxx from '*.vue' 视为组件对象，避免找不到模块声明。
declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

// ==================== 环境变量类型 ====================
// VITE_API_BASE_URL：后端接口基础地址；VITE_APP_TITLE：浏览器标题中的应用名。
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string
  readonly VITE_APP_TITLE: string
}

// 将自定义环境变量挂到 import.meta.env 上，提供只读的类型提示。
interface ImportMeta {
  readonly env: ImportMetaEnv
}
