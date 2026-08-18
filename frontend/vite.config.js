import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      // 开发模式下代理到后端
      '/api': 'http://127.0.0.1:8000'
    }
  },
  build: {
    outDir: 'dist',
    emptyOutDir: false, // 沙箱环境回收站不可用，避免 vite 清理 dist 时报错
    chunkSizeWarningLimit: 2000
  }
})
