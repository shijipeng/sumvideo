import { app, BrowserWindow, dialog, ipcMain } from 'electron'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { getElectronProfile } from '../config/env.mjs'
import { ensureBackend, stopBackend } from './backend-lifecycle.mjs'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.join(__dirname, '..')
const BACKEND_DIR = path.join(ROOT, 'backend')
const WEB_DIST = path.join(ROOT, 'web', 'dist', 'index.html')

const isDev = process.env.SUMVIDEO_DEV === '1'
const profile = getElectronProfile({ isPackaged: app.isPackaged, isElectronDev: isDev })

const API_HOST = process.env.SUMVIDEO_BACKEND_HOST || profile.backend.host
const API_PORT = Number(process.env.SUMVIDEO_BACKEND_PORT || profile.backend.port)
const API_BASE_URL =
  process.env.SUMVIDEO_BACKEND_URL ||
  profile.backend.url ||
  `http://${API_HOST}:${API_PORT}`

process.env.SUMVIDEO_ENV = app.isPackaged ? 'desktop' : 'dev'
process.env.SUMVIDEO_API_PORT = String(API_PORT)
process.env.SUMVIDEO_BACKEND_URL = API_BASE_URL
process.env.SUMVIDEO_API_BASE_URL = API_BASE_URL

function getUserDataDir() {
  // 未打包（npx electron . / desktop:dev）：与 Web 开发共用 backend/，模型目录一致
  if (!app.isPackaged) return BACKEND_DIR
  return path.join(app.getPath('userData'), 'SumVideo')
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 840,
    minWidth: 900,
    minHeight: 600,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  if (isDev && profile.electron.loadFrontendDevServer) {
    const devUrl =
      process.env.SUMVIDEO_FRONTEND_URL ||
      getElectronProfile({ isPackaged: false, isElectronDev: true }).frontend.url
    win.loadURL(devUrl)
    win.webContents.openDevTools({ mode: 'detach' })
  } else {
    win.loadFile(WEB_DIST)
  }
}

app.whenReady().then(async () => {
  const dataDir = getUserDataDir()
  process.env.SUMVIDEO_DATA_DIR = dataDir

  console.log(
    `[SumVideo] 环境=${process.env.SUMVIDEO_ENV} API=${API_BASE_URL} 数据=${dataDir}`,
  )

  if (process.resourcesPath) {
    const ffmpegBundled = path.join(
      process.resourcesPath,
      'bin',
      process.platform === 'win32' ? 'ffmpeg.exe' : 'ffmpeg',
    )
    if (fs.existsSync(ffmpegBundled)) {
      process.env.SUMVIDEO_FFMPEG = ffmpegBundled
    }
  }

  await ensureBackend({
    backendDir: BACKEND_DIR,
    dataDir,
    port: API_PORT,
    resourcesPath: app.isPackaged ? process.resourcesPath : null,
    allowReuse: profile.electron.reuseBackend,
  })

  ipcMain.handle('pick-video', async () => {
    const result = await dialog.showOpenDialog({
      properties: ['openFile'],
      filters: [
        {
          name: 'Video',
          extensions: [
            'mp4', 'm4v', 'avi', 'mov', 'mkv', 'webm', 'flv', 'wmv',
            'mpeg', 'mpg', '3gp', 'ts',
          ],
        },
      ],
    })
    if (result.canceled || !result.filePaths[0]) return null
    const filePath = result.filePaths[0]
    return { path: filePath, name: path.basename(filePath) }
  })

  ipcMain.handle('read-video-file', async (_event, filePath, name) => {
    const resolved = path.resolve(String(filePath || ''))
    if (!resolved || !fs.existsSync(resolved)) {
      throw new Error('文件不存在或不可读')
    }
    const stat = await fs.promises.stat(resolved)
    if (!stat.isFile()) {
      throw new Error('路径不是文件')
    }
    const buf = await fs.promises.readFile(resolved)
    const fileName = String(name || path.basename(resolved))
    return {
      name: fileName,
      buffer: buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength),
    }
  })

  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  stopBackend()
})
