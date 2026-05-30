/** Web / Electron 运行时探测与桌面能力 */

import { webConfiguredApiBase } from './env'

export interface PickedVideo {
  path: string
  name: string
}

export interface ReadVideoFileResult {
  name: string
  buffer: ArrayBuffer
}

export interface SumVideoDesktopBridge {
  isDesktop: boolean
  pickVideo: () => Promise<PickedVideo | null>
  readVideoFile: (filePath: string, name?: string) => Promise<ReadVideoFileResult>
  getApiBase: () => string
}

declare global {
  interface Window {
    sumvideo?: SumVideoDesktopBridge
  }
}

export function isDesktop(): boolean {
  return Boolean(window.sumvideo?.isDesktop)
}

export function getApiBase(): string {
  const desktop = window.sumvideo?.getApiBase?.()
  if (desktop) return desktop.replace(/\/$/, '')
  return webConfiguredApiBase()
}

export function apiUrl(path: string): string {
  const p = path.startsWith('/') ? path : `/${path}`
  const base = getApiBase()
  return base ? `${base}${p}` : p
}

export async function pickVideoFile(): Promise<PickedVideo | null> {
  if (!window.sumvideo?.pickVideo) return null
  return window.sumvideo.pickVideo()
}

const VIDEO_MIME: Record<string, string> = {
  '.mp4': 'video/mp4',
  '.m4v': 'video/x-m4v',
  '.mov': 'video/quicktime',
  '.webm': 'video/webm',
  '.mkv': 'video/x-matroska',
  '.avi': 'video/x-msvideo',
}

function guessVideoMime(filename: string): string {
  const ext = filename.includes('.')
    ? filename.slice(filename.lastIndexOf('.')).toLowerCase()
    : ''
  return VIDEO_MIME[ext] || 'application/octet-stream'
}

export async function readVideoAsFile(filePath: string, name: string): Promise<File> {
  if (!window.sumvideo?.readVideoFile) {
    throw new Error('桌面环境未就绪，无法读取本地视频')
  }
  const { name: fileName, buffer } = await window.sumvideo.readVideoFile(filePath, name)
  return new File([buffer], fileName, { type: guessVideoMime(fileName) })
}
