import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import path from 'path'

export default defineConfig({
  plugins: [
    vue(),
    AutoImport({
      resolvers: [ElementPlusResolver()],
    }),
    Components({
      resolvers: [ElementPlusResolver()],
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    // Docker 内必须监听 0.0.0.0 才能对外暴露端口；本地 npm run dev 也无副作用
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    cors: true,
    // Windows + Docker bind mount 下 inotify 事件不可靠，用轮询保证热重载触发
    watch: process.env.DOCKER_RUNNING === '1'
      ? { usePolling: true, interval: 500 }
      : undefined,
    hmr: {
      // HMR WebSocket 从浏览器(宿主机)连回时用 127.0.0.1:5173，避免容器内地址导致连不上
      host: '127.0.0.1',
      clientPort: 5173,
    },
    proxy: {
      '/api': {
        // 本地开发默认宿主机 127.0.0.1:8000；Docker 内通过环境变量改为 compose 服务名 http://app:8000
        target: process.env.VITE_PROXY_TARGET ?? 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
