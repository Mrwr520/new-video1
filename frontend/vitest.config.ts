import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src/renderer')
    }
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/renderer/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    // 主进程测试使用 Node 环境
    environmentMatchGlobs: [
      ['src/main/**/*.test.ts', 'node']
    ]
  }
})
