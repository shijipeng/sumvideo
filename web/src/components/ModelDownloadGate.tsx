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

export function ModelDownloadGate({ onComplete, onBackToSettings }: Props) {
  const [hint, setHint] = useState<ModelDownloadHint | null>(null)
  const [progress, setProgress] = useState(0)
  const [message, setMessage] = useState('')
  const [status, setStatus] = useState<'idle' | 'downloading' | 'done' | 'error'>('idle')
  const [error, setError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const completedRef = useRef(false)

  const applyDownloadState = useCallback((s: ModelDownloadState) => {
    setProgress(s.progress ?? 0)
    setMessage(s.message || '')
    setStatus(s.status as typeof status)
    if (s.error) setError(s.error)
    else if (s.status !== 'error') setError(null)
  }, [])

  const finishIfDone = useCallback(
    (s: ModelDownloadState) => {
      if (completedRef.current) return
      if (s.status === 'done' || s.model_ready) {
        completedRef.current = true
        onComplete()
      }
    },
    [onComplete],
  )

  // 进入页面即轮询，与后端下载进度保持同步
  useEffect(() => {
    let active = true

    getModelStatus()
      .then((data) => {
        if (!active) return
        setHint(data.hint)
        applyDownloadState(data.download)
        if (data.cached && data.download.status !== 'downloading') {
          finishIfDone({ ...data.download, status: 'done', model_ready: true })
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
        finishIfDone(s)
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
    try {
      const res = await startModelDownload()
      applyDownloadState(res.download)
      finishIfDone(res.download)
      // 立即再拉一次，避免等下一个轮询周期
      const latest = await getModelDownloadStatus()
      applyDownloadState(latest)
      finishIfDone(latest)
    } catch (e) {
      setError(formatUnknownError(e, '无法开始下载'))
      setStatus('error')
    } finally {
      setStarting(false)
    }
  }

  const showProgress = status === 'downloading' || starting

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

        <div className="mt-6 rounded-lg border border-zinc-800 bg-zinc-950/50 p-4 text-sm text-zinc-300">
          <p>
            <span className="text-zinc-500">模型：</span>
            {hint.label}
          </p>
          <p className="mt-2">
            <span className="text-zinc-500">约 </span>
            {hint.size_gb} GB，{hint.eta_text}
          </p>
          <p className="mt-2 text-xs text-zinc-500">保存目录：{hint.cache_dir}</p>
          <p className="mt-1 text-xs text-zinc-500">下载源：{hint.mirror_hint}</p>
        </div>

        {showProgress && (
          <div className="mt-6">
            <div className="mb-1 flex justify-between text-xs text-zinc-500">
              <span>{message || (starting ? '启动下载…' : '下载中…')}</span>
              <span>{Math.max(progress, starting ? 1 : 0)}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-zinc-800">
              <div
                className="h-full bg-[var(--sv-accent)] transition-all duration-300"
                style={{ width: `${Math.max(progress, showProgress ? 2 : 0)}%` }}
              />
            </div>
            <p className="mt-2 text-xs text-zinc-500">
              进度每 {POLL_MS / 1000} 秒与后端同步。请勿关闭后端终端，完成后自动进入主界面。
            </p>
          </div>
        )}

        {status === 'error' && !error && (
          <p className="mt-4 text-sm text-red-300">下载失败，请重试或检查网络。</p>
        )}

        {error && (
          <p className="mt-4 rounded-lg bg-red-900/30 px-3 py-2 text-sm text-red-300">{error}</p>
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
            className="w-full rounded-xl bg-zinc-800 py-3 text-sm text-zinc-300 hover:bg-zinc-700"
          >
            返回修改设置
          </button>
        </div>
      </div>
    </div>
  )
}
