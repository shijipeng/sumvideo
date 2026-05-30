import { useCallback, useEffect, useRef, useState } from 'react'
import {
  getModelDownloadStatus,
  getModelStatus,
  startModelDownload,
} from '../lib/api'
import type { ModelDownloadHint, ModelDownloadState } from '../types'
import { formatUnknownError } from '../lib/errors'

interface Props {
  onComplete: () => void
  onBackToSettings: () => void
}

const POLL_MS = 800

function formatBytes(n?: number): string | null {
  if (n == null || n <= 0) return null
  const mb = n / (1024 * 1024)
  if (mb >= 1024) return `${(mb / 1024).toFixed(2)} GB`
  return `${mb.toFixed(1)} MB`
}

export function ModelDownloadGate({ onComplete, onBackToSettings }: Props) {
  const [hint, setHint] = useState<ModelDownloadHint | null>(null)
  const [progress, setProgress] = useState(0)
  const [message, setMessage] = useState('')
  const [bytesDownloaded, setBytesDownloaded] = useState<number | undefined>()
  const [bytesTotal, setBytesTotal] = useState<number | undefined>()
  const [status, setStatus] = useState<'idle' | 'downloading' | 'done' | 'error'>('idle')
  const [error, setError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const completedRef = useRef(false)

  const applyDownloadState = useCallback((s: ModelDownloadState) => {
    setProgress(s.progress ?? 0)
    setMessage(s.message || '')
    setBytesDownloaded(s.bytes_downloaded)
    setBytesTotal(s.bytes_total)
    setStatus(s.status as typeof status)
    if (s.error) setError(s.error)
    else if (s.status !== 'error') setError(null)
  }, [])

  const finishIfDone = useCallback(
    (ready?: boolean) => {
      if (completedRef.current || !ready) return
      completedRef.current = true
      onComplete()
    },
    [onComplete],
  )

  useEffect(() => {
    let active = true

    getModelStatus()
      .then((data) => {
        if (!active) return
        setHint(data.hint)
        applyDownloadState(data.download)
        if (data.cached && data.download.status !== 'downloading') {
          finishIfDone(true)
        }
      })
      .catch((e) => {
        if (active) setError(formatUnknownError(e, '加载失败'))
      })

    const tick = async () => {
      try {
        const s = await getModelDownloadStatus()
        if (!active) return
        applyDownloadState(s)
        finishIfDone(s.model_ready)
      } catch (e) {
        if (active) setError(formatUnknownError(e, '获取下载状态失败'))
      }
    }

    tick()
    const id = window.setInterval(tick, POLL_MS)
    return () => {
      active = false
      window.clearInterval(id)
    }
  }, [applyDownloadState, finishIfDone])

  const handleStart = async () => {
    setError(null)
    setStarting(true)
    setStatus('downloading')
    setProgress(0)
    setMessage('准备下载…')
    setBytesDownloaded(undefined)
    setBytesTotal(undefined)
    try {
      const res = await startModelDownload()
      applyDownloadState(res.download)
      finishIfDone(res.cached || res.download.model_ready)
      const latest = await getModelDownloadStatus()
      applyDownloadState(latest)
      finishIfDone(latest.model_ready)
    } catch (e) {
      setError(formatUnknownError(e, '无法开始下载'))
      setStatus('error')
    } finally {
      setStarting(false)
    }
  }

  const showProgress = status === 'downloading' || starting
  const downloadedLabel = formatBytes(bytesDownloaded)
  const totalLabel = formatBytes(bytesTotal)
  const sizeLine =
    downloadedLabel && totalLabel
      ? `${downloadedLabel} / ${totalLabel}`
      : downloadedLabel
        ? `已下载 ${downloadedLabel}`
        : null
  const barPercent =
    bytesDownloaded != null && bytesTotal != null && bytesTotal > 0
      ? Math.min(100, Math.max(1, Math.round((bytesDownloaded * 100) / bytesTotal)))
      : Math.min(100, Math.max(progress, showProgress ? 1 : 0))

  if (!hint) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-[var(--sv-bg)] text-[var(--sv-fg-muted)]">
        加载模型信息…
      </div>
    )
  }

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center bg-[var(--sv-bg)] px-4">
      <div className="w-full max-w-lg rounded-2xl border border-[var(--sv-border)] bg-[var(--sv-canvas)] p-8 shadow-xl">
        <h1 className="text-2xl font-semibold text-[var(--sv-fg)]">下载 Whisper 模型</h1>
        <p className="mt-2 text-sm text-[var(--sv-fg-muted)]">
          你已选择转写模型，需先下载到本机后才能处理视频。下载只需进行一次（每个模型各一次）。
        </p>

        <div className="mt-6 rounded-lg border border-[var(--sv-border)] bg-[var(--sv-canvas-subtle)] p-4 text-sm text-[var(--sv-fg)]">
          <p>
            <span className="text-[var(--sv-fg-muted)]">模型：</span>
            {hint.label}
          </p>
          <p className="mt-2">
            <span className="text-[var(--sv-fg-muted)]">约 </span>
            {hint.size_gb} GB，{hint.eta_text}
          </p>
          <p className="mt-2 text-xs text-[var(--sv-fg-muted)]">保存目录：{hint.cache_dir}</p>
          <p className="mt-1 text-xs text-[var(--sv-fg-muted)]">下载源：{hint.mirror_hint}</p>
        </div>

        {showProgress && (
          <div className="mt-6">
            <div className="mb-1 flex justify-between text-xs text-[var(--sv-fg-muted)]">
              <span className="min-w-0 flex-1 truncate pr-2">
                {message || (starting ? '启动下载…' : '下载中…')}
              </span>
              <span className="shrink-0 tabular-nums">{barPercent}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-[var(--sv-canvas-subtle)]">
              <div
                className="h-full bg-[var(--sv-accent)] transition-all duration-300"
                style={{ width: `${barPercent}%` }}
              />
            </div>
            {sizeLine && (
              <p className="mt-2 text-xs tabular-nums text-[var(--sv-fg)]">{sizeLine}</p>
            )}
            <p className="mt-2 text-xs text-[var(--sv-fg-muted)]">
              下载中数据写在{' '}
              <span className="font-mono text-[var(--sv-fg)]">models/…/blobs/*.incomplete</span>
              {' '}临时文件里；完成后才会在{' '}
              <span className="font-mono text-[var(--sv-fg)]">snapshots/</span>{' '}
              出现 <span className="font-mono">weights.safetensors</span>。用终端{' '}
              <span className="font-mono">du -sh {hint.cache_dir}</span> 查看总占用最准确。
            </p>
            <p className="mt-1 text-xs text-[var(--sv-fg-muted)]">
              进度每 {POLL_MS / 1000} 秒与后端同步。请勿关闭后端，完成后自动进入主界面。
            </p>
          </div>
        )}

        {status === 'error' && !error && (
          <p className="mt-4 text-sm text-[var(--sv-danger-fg)]">下载失败，请重试或检查网络。</p>
        )}

        {error && (
          <p className="mt-4 rounded-lg bg-[var(--sv-danger-bg)] px-3 py-2 text-sm text-[var(--sv-danger-fg)]">
            {error}
          </p>
        )}

        <div className="mt-8 flex flex-col gap-3">
          {!showProgress && status !== 'done' && (
            <button
              type="button"
              disabled={starting}
              onClick={handleStart}
              className="w-full rounded-xl bg-[var(--sv-accent)] py-3 text-sm font-medium text-[var(--sv-accent-fg)] hover:opacity-90 disabled:opacity-50"
            >
              {starting ? '启动中…' : '开始下载'}
            </button>
          )}
          <button
            type="button"
            onClick={onBackToSettings}
            className="w-full rounded-xl border border-[var(--sv-border)] bg-[var(--sv-canvas-subtle)] py-3 text-sm text-[var(--sv-fg)] hover:opacity-90"
          >
            返回修改设置
          </button>
        </div>
      </div>
    </div>
  )
}
