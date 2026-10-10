import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 前端：dev 用 3001。
// /api 经 vite proxy 转发到后端 8000 —— 同源请求，不触发 CORS，
// 因此后端 .env 的 CORS_ORIGINS 无需为本站改动。
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3001,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
