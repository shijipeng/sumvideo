import type {
  AppSettings,
  HistoryItem,
  ModelDownloadHint,
  ModelDownloadState,
  UploadResponse,
  VideoStatus,
} from '../types'
import { parseApiError } from './errors'
import { connectionHint } from './env'
import { apiUrl } from './runtime'

const DEFAULT_TIMEOUT_MS = 12_000

async function fetchWithTimeout(
  url: string,
  init?: RequestInit,
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await fetch(url, { ...init, signal: controller.signal })
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') {
      throw new Error('请求超时：后端可能正在处理视频，请稍后再试或重启后端')
    }
    throw new Error(`无法连接后端。${connectionHint()}`)
  } finally {
    window.clearTimeout(timer)
  }
}

export async function getSettings(): Promise<AppSettings> {
  const res = await fetchWithTimeout(apiUrl('/api/settings'))
  if (!res.ok) throw new Error('无法读取设置')
  return res.json()
}

export async function saveSettings(payload: {
  api_key?: string
  whisper_model: string
  deepseek_model: string
}): Promise<{ ready: boolean; message: string }> {
  const res = await fetch(apiUrl('/api/settings'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(parseApiError(err, '保存失败'))
  }
  return res.json()
}

export async function clearSettings(): Promise<void> {
  const res = await fetch(apiUrl('/api/settings'), { method: 'DELETE' })
  if (!res.ok) throw new Error('清除失败')
}

export async function getModelStatus(): Promise<{
  model_id: string
  cached: boolean
  hint: ModelDownloadHint
  download: ModelDownloadState
}> {
  const res = await fetch(apiUrl('/api/models/status'))
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(parseApiError(err, '无法获取模型状态'))
  }
  return res.json()
}

export async function startModelDownload(): Promise<{
  started: boolean
  cached: boolean
  message: string
  download: ModelDownloadState
}> {
  const res = await fetch(apiUrl('/api/models/download'), { method: 'POST' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(parseApiError(err, '无法开始下载'))
  }
  return res.json()
}

export async function getModelDownloadStatus(): Promise<ModelDownloadState> {
  const res = await fetch(apiUrl('/api/models/download/status'))
  if (!res.ok) throw new Error('无法获取下载进度')
  return res.json()
}

export async function uploadVideo(file: File, force = false): Promise<UploadResponse> {
  const form = new FormData()
  form.append('file', file)
  const url = force ? apiUrl('/api/upload?force=true') : apiUrl('/api/upload')
  const res = await fetch(url, { method: 'POST', body: form })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(parseApiError(err, `上传失败 (HTTP ${res.status})`))
  }
  return res.json()
}

export async function importVideoUrl(url: string, force = false): Promise<UploadResponse> {
  const res = await fetch(apiUrl('/api/import-url'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, force }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(parseApiError(err, `导入失败 (HTTP ${res.status})`))
  }
  return res.json()
}

export async function getStatus(taskId: string): Promise<VideoStatus> {
  // 处理中长视频时后端忙于转写/DeepSeek，轮询放宽超时
  const res = await fetchWithTimeout(apiUrl(`/api/status/${taskId}`), undefined, 60_000)
  if (!res.ok) {
    if (res.status === 404) throw new Error('任务不存在（可能已删除或后端已重置）')
    throw new Error(`获取状态失败 (HTTP ${res.status})`)
  }
  return res.json()
}

export type RetryFromStage = 'auto' | 'full' | 'notes_only' | 'frames_only'

export async function retryVideo(
  taskId: string,
  fromStage: RetryFromStage = 'auto',
): Promise<{ message: string; task_id: string; resume_mode?: string }> {
  const q = fromStage === 'auto' ? '' : `?from_stage=${encodeURIComponent(fromStage)}`
  const res = await fetch(apiUrl(`/api/retry/${taskId}${q}`), { method: 'POST' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(parseApiError(err, `重新处理失败 (HTTP ${res.status})`))
  }
  return res.json()
}

export async function getHistory(): Promise<HistoryItem[]> {
  const res = await fetchWithTimeout(apiUrl('/api/history'))
  if (!res.ok) throw new Error('获取历史失败')
  return res.json()
}

export async function deleteHistory(id: string): Promise<void> {
  const res = await fetch(apiUrl(`/api/history/${id}`), { method: 'DELETE' })
  if (!res.ok) throw new Error('删除失败')
}

export function videoStreamUrl(taskId: string) {
  return apiUrl(`/api/video/${taskId}`)
}

export function sectionThumbUrl(videoId: string, sectionIndex: number, frameIndex = 0) {
  return apiUrl(`/api/video/${videoId}/thumb/${sectionIndex}/${frameIndex}`)
}

export function resolveSectionThumbUrl(thumbnail: string | null | undefined) {
  if (!thumbnail) return null
  if (thumbnail.startsWith('http://') || thumbnail.startsWith('https://')) {
    return thumbnail
  }
  return apiUrl(thumbnail)
}

export function exportMindmapMd(filename: string, markdown: string) {
  const base = filename.replace(/\.[^.]+$/, '') || 'mindmap'
  const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${base}-mindmap.md`
  a.click()
  URL.revokeObjectURL(a.href)
}

export function exportNotesMd(
  filename: string,
  overview: string,
  sections: {
    title: string
    start_time: number
    lead?: string
    points?: string[]
  }[],
) {
  const lines = [`# ${filename} 笔记\n`, '## 概述\n', overview || '（无）', '\n## 分段笔记\n']
  for (const sec of sections) {
    const m = Math.floor(sec.start_time / 60)
    const s = Math.floor(sec.start_time % 60)
    lines.push(`\n### ${sec.title} (${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')})\n`)
    if (sec.lead) lines.push(`${sec.lead}\n`)
    for (const p of sec.points ?? []) {
      lines.push(`- ${p}`)
    }
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = 'summary.md'
  a.click()
  URL.revokeObjectURL(a.href)
}
