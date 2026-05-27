import { useCallback, useEffect, useRef, useState } from 'react'
import { getStatus } from '../lib/api'
import type { VideoStatus } from '../types'

export function useTaskPolling(taskId: string | null, enabled: boolean) {
  const [status, setStatus] = useState<VideoStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const timerRef = useRef<number | null>(null)

  const poll = useCallback(async () => {
    if (!taskId) return
    try {
      const data = await getStatus(taskId)
      setStatus(data)
      setError(null)
      if (data.status === 'done' || data.status === 'error') {
        if (timerRef.current) {
          window.clearInterval(timerRef.current)
          timerRef.current = null
        }
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : '轮询失败'
      setError(msg)
      if (msg.includes('失败') || msg.includes('404')) {
        if (timerRef.current) {
          window.clearInterval(timerRef.current)
          timerRef.current = null
        }
      }
    }
  }, [taskId])

  useEffect(() => {
    if (!taskId || !enabled) {
      setStatus(null)
      return
    }
    poll()
    timerRef.current = window.setInterval(poll, 800)
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current)
    }
  }, [taskId, enabled, poll])

  return { status, error, refresh: poll }
}
