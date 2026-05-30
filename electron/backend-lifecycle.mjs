import { spawn } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

let backendProc = null
let spawnedByElectron = false

function resolvePython(backendDir, resourcesPath) {
  if (process.env.SUMVIDEO_PYTHON) {
    return process.env.SUMVIDEO_PYTHON
  }
  if (resourcesPath) {
    const bundled = path.join(
      resourcesPath,
      'venv',
      process.platform === 'win32' ? 'Scripts' : 'bin',
      process.platform === 'win32' ? 'python.exe' : 'python',
    )
    if (fs.existsSync(bundled)) return bundled
  }
  const devVenv =
    process.platform === 'win32'
      ? path.join(backendDir, '.venv', 'Scripts', 'python.exe')
      : path.join(backendDir, '.venv', 'bin', 'python')
  if (fs.existsSync(devVenv)) return devVenv
  return process.platform === 'win32' ? 'python' : 'python3'
}

export async function isBackendHealthy(port) {
  try {
    const res = await fetch(`http://127.0.0.1:${port}/api/settings`)
    return res.ok
  } catch {
    return false
  }
}

async function waitForHealth(port, maxMs = 60000) {
  const start = Date.now()
  while (Date.now() - start < maxMs) {
    try {
      const res = await fetch(`http://127.0.0.1:${port}/api/settings`)
      if (res.ok) return true
    } catch {
      /* retry */
    }
    await new Promise((r) => setTimeout(r, 400))
  }
  return false
}

async function fetchBackendDataDir(port) {
  try {
    const res = await fetch(`http://127.0.0.1:${port}/api/settings`)
    if (!res.ok) return null
    const data = await res.json()
    return data.data_dir || null
  } catch {
    return null
  }
}

/**
 * 拉起或复用后端（只认目标 port，不会去连 Web 的 8000）。
 * allowReuse=true：desktop:dev 可共用 npm run backend（8000 + backend/）。
 * allowReuse=false：安装包用 8001；若 8001 上已有本应用后端则复用，否则新建。
 */
export async function ensureBackend({
  backendDir,
  dataDir,
  port,
  resourcesPath,
  allowReuse = false,
}) {
  if (await isBackendHealthy(port)) {
    const remoteDataDir = await fetchBackendDataDir(port)
    const expected = path.resolve(dataDir)
    if (remoteDataDir && path.resolve(remoteDataDir) !== expected) {
      throw new Error(
        `端口 ${port} 上已有后端，但数据目录不一致。\n` +
          `  本窗口期望: ${expected}\n` +
          `  当前后端实际: ${remoteDataDir}\n` +
          `请先结束占用 ${port} 的进程（如 npm run backend），再启动桌面端。`,
      )
    }
    const tag = allowReuse ? '开发/Web 共享' : '桌面独立'
    const base = process.env.SUMVIDEO_BACKEND_URL || `http://127.0.0.1:${port}`
    console.log(`[SumVideo] 复用 ${tag} 后端 ${base}`)
    return
  }
  await startBackend({ backendDir, dataDir, port, resourcesPath })
}

export async function startBackend({ backendDir, dataDir, port, resourcesPath }) {
  if (backendProc) return

  fs.mkdirSync(dataDir, { recursive: true })
  spawnedByElectron = true

  const packagedBackend =
    resourcesPath && fs.existsSync(path.join(resourcesPath, 'backend', 'app.py'))
      ? path.join(resourcesPath, 'backend')
      : backendDir

  const python = resolvePython(packagedBackend, resourcesPath)
  const env = {
    ...process.env,
    SUMVIDEO_DATA_DIR: dataDir,
    PYTHONUNBUFFERED: '1',
  }

  backendProc = spawn(
    python,
    ['-m', 'uvicorn', 'app:app', '--host', '127.0.0.1', '--port', String(port)],
    {
      cwd: packagedBackend,
      env,
      stdio: 'inherit',
    },
  )

  backendProc.on('exit', (code) => {
    console.error('[SumVideo] backend exited', code)
    backendProc = null
  })

  const ok = await waitForHealth(port)
  if (!ok) {
    throw new Error(`后端未在 ${port} 端口就绪，请检查 Python 环境与依赖`)
  }
}

export function stopBackend() {
  if (!backendProc || !spawnedByElectron) return
  backendProc.kill()
  backendProc = null
  spawnedByElectron = false
}
