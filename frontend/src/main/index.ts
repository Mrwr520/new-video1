import { app, BrowserWindow, dialog, globalShortcut, shell } from 'electron'
import { join } from 'path'
import { is } from '@electron-toolkit/utils'
import { PythonManager } from './python-manager'

let pythonManager: PythonManager | null = null

function createPythonManager(): PythonManager {
  const backendDir = is.dev
    ? join(app.getAppPath(), '..', 'backend')
    : join(process.resourcesPath, 'backend')

  const manager = new PythonManager({
    pythonPath: 'python',
    backendPort: 8000,
    backendDir,
    healthCheckInterval: 5000,
    startTimeout: 30000
  })

  // Requirement 9.3: 启动失败时显示诊断信息
  manager.on('diagnostic', (info) => {
    dialog.showErrorBox(
      'Python 后端启动失败',
      `错误: ${info.error}\n\n` +
        `Python 路径: ${info.pythonPath}\n` +
        `退出码: ${info.exitCode ?? '无'}\n\n` +
        `诊断信息:\n${info.stderr || '无'}\n\n` +
        `请检查:\n` +
        `1. Python 是否已安装且在 PATH 中\n` +
        `2. 是否已安装所需依赖 (pip install -r requirements.txt)\n` +
        `3. 端口 8000 是否被占用`
    )
  })

  // Requirement 9.5: 崩溃时提供自动重启选项
  manager.on('crash', async () => {
    const { response } = await dialog.showMessageBox({
      type: 'error',
      title: 'Python 后端异常',
      message: 'Python 后端服务已停止运行',
      detail: '是否尝试重新启动后端服务？',
      buttons: ['重新启动', '忽略'],
      defaultId: 0
    })

    if (response === 0) {
      try {
        await manager.restart()
      } catch {
        // restart 失败会触发 diagnostic 事件
      }
    }
  })

  return manager
}

function createWindow(): void {
  const mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    show: false,
    autoHideMenuBar: true,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      contextIsolation: true,
      nodeIntegration: false
    }
  })

  mainWindow.on('ready-to-show', () => {
    mainWindow.show()
  })

  // 注册刷新快捷键
  mainWindow.webContents.on('before-input-event', (_event, input) => {
    if (input.key === 'F5' || (input.control && input.key === 'r')) {
      mainWindow.webContents.reload()
    }
    if (input.key === 'F12') {
      mainWindow.webContents.toggleDevTools()
    }
  })

  mainWindow.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url)
    return { action: 'deny' }
  })

  // 开发模式加载 dev server，生产模式加载打包文件
  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

app.whenReady().then(async () => {
  createWindow()

  // Requirement 9.1: 启动时自动启动 Python 后端
  pythonManager = createPythonManager()
  try {
    await pythonManager.start()
    console.log('Python 后端已启动')
  } catch (err) {
    console.error('Python 后端启动失败:', err)
    // 诊断信息已通过 diagnostic 事件展示给用户
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

// Requirement 9.2: 关闭时安全终止 Python 后端
app.on('before-quit', async (event) => {
  if (pythonManager && pythonManager.getStatus() !== 'stopped') {
    event.preventDefault()
    try {
      await pythonManager.stop()
      console.log('Python 后端已安全终止')
    } catch (err) {
      console.error('Python 后端终止失败:', err)
    }
    app.quit()
  }
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})
