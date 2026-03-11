import { contextBridge } from 'electron'

// 暴露 API 到渲染进程
contextBridge.exposeInMainWorld('electronAPI', {
  platform: process.platform
})
