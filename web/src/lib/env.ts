/**
 * 前端运行时环境（构建时由 Vite 注入，与 config/environments.json 同步）
 */
declare const __SUMVIDEO_DEV_BACKEND_URL__: string
declare const __SUMVIDEO_DEV_FRONTEND_URL__: string

/** 浏览器开发：留空走 Vite 代理；桌面/Electron 由 preload 提供 API 根地址 */
export function webConfiguredApiBase(): string {
  const raw = import.meta.env.VITE_SUMVIDEO_API_BASE as string | undefined
  if (raw?.trim()) return raw.trim().replace(/\/$/, '')
  return ''
}

/** 开发环境后端地址（用于错误提示） */
export function devBackendUrl(): string {
  return typeof __SUMVIDEO_DEV_BACKEND_URL__ !== 'undefined'
    ? __SUMVIDEO_DEV_BACKEND_URL__
    : 'http://127.0.0.1:8000'
}

export function devFrontendUrl(): string {
  return typeof __SUMVIDEO_DEV_FRONTEND_URL__ !== 'undefined'
    ? __SUMVIDEO_DEV_FRONTEND_URL__
    : 'http://127.0.0.1:5173'
}

export function connectionHint(): string {
  if (import.meta.env.DEV) {
    return `请先执行 npm run backend（${devBackendUrl()}），并确保 npm run frontend（${devFrontendUrl()}）已启动`
  }
  return '请确认桌面应用后端已启动'
}
