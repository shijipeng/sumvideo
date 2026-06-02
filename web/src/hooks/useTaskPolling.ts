import { useCallback, useEffect, useRef, useState } from 'react'
import { getStatus } from '../lib/api'
import type { VideoStatus } from '../types'

function frameStillRunning(data: VideoStatus): boolean {
  return (
    data.status === 'done' &&
    (data.frame_status === 'pending' || data.frame_status === 'processing')
  )
}

function shouldStopPolling(data: VideoStatus): boolean {
  if (data.status === 'error') return true
  if (data.status === 'done' && !frameStillRunning(data)) return true
  return false
}

export function useTaskPolling(taskId: string | null, enabled: boolean) {
  const [status, setStatus] = useState<VideoStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const timerRef = useRef<number | null>(null)

  const clearTimer = () => {
    if (timerRef.current) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
  }

  const poll = useCallback(async () => {
    if (!taskId) return
    try {
      const data = await getStatus(taskId)
      setStatus(data)
      setError(null)
      if (shouldStopPolling(data)) {
        clearTimer()
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : '轮询失败'
      setError(msg)
      if (msg.includes('失败') || msg.includes('404')) {
        clearTimer()
      }
    }
  }, [taskId])

  useEffect(() => {
    if (!taskId || !enabled) {
      setStatus(null)
      clearTimer()
      return
    }
    poll()
    clearTimer()
    timerRef.current = window.setInterval(poll, 800)
    return clearTimer
  }, [taskId, enabled, poll])

  return { status, error, refresh: poll }
}
