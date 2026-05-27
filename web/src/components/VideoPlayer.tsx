import { useCallback, useEffect, useImperativeHandle, useRef, forwardRef } from 'react'

export interface VideoPlayerHandle {
  seekTo: (seconds: number) => void
  getCurrentTime: () => number
}

interface Props {
  src: string | null
  onTimeUpdate?: (time: number) => void
}

const SEEK_STEP = 10
const FAST_FORWARD_RATE = 2
const HOLD_FOR_FF_MS = 350

export const VideoPlayer = forwardRef<VideoPlayerHandle, Props>(function VideoPlayer(
  { src, onTimeUpdate },
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const onTimeUpdateRef = useRef(onTimeUpdate)
  onTimeUpdateRef.current = onTimeUpdate

  const holdTimerRef = useRef<number | null>(null)
  const fastForwardRef = useRef(false)
  const rightKeyDownRef = useRef(false)

  const focusContainer = useCallback(() => {
    containerRef.current?.focus({ preventScroll: true })
  }, [])

  useImperativeHandle(ref, () => ({
    seekTo(seconds: number) {
      const video = videoRef.current
      if (!video) return
      fastForwardRef.current = false
      video.playbackRate = 1
      video.currentTime = Math.max(0, seconds)
      void video.play().catch(() => {})
      requestAnimationFrame(focusContainer)
    },
    getCurrentTime() {
      return videoRef.current?.currentTime ?? 0
    },
  }))

  useEffect(() => {
    const video = videoRef.current
    if (!video || !src) return

    const clearHoldTimer = () => {
      if (holdTimerRef.current !== null) {
        window.clearTimeout(holdTimerRef.current)
        holdTimerRef.current = null
      }
    }

    const stopFastForward = () => {
      if (!fastForwardRef.current) return
      fastForwardRef.current = false
      video.playbackRate = 1
    }

    const startFastForward = () => {
      if (fastForwardRef.current) return
      fastForwardRef.current = true
      video.playbackRate = FAST_FORWARD_RATE
      void video.play().catch(() => {})
    }

    const onTick = () => onTimeUpdateRef.current?.(video.currentTime)
    video.addEventListener('timeupdate', onTick)

    const isBlockedTarget = (target: EventTarget | null) => {
      const el = target as HTMLElement | null
      if (!el) return false
      const tag = el.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true
      return Boolean(el.closest('[data-notes-panel]'))
    }

    const onKeyDown = (e: KeyboardEvent) => {
      if (isBlockedTarget(e.target)) return

      if (e.key === 'ArrowRight') {
        e.preventDefault()
        e.stopImmediatePropagation()

        if (!rightKeyDownRef.current) {
          rightKeyDownRef.current = true
          clearHoldTimer()
          holdTimerRef.current = window.setTimeout(startFastForward, HOLD_FOR_FF_MS)
        }
        return
      }

      if (e.key === 'ArrowLeft') {
        e.preventDefault()
        e.stopImmediatePropagation()
        if (e.repeat) return
        stopFastForward()
        clearHoldTimer()
        rightKeyDownRef.current = false
        video.currentTime = Math.max(0, video.currentTime - SEEK_STEP)
        return
      }

      if (e.key === ' ') {
        const active = document.activeElement
        if (containerRef.current?.contains(active) || active === video) {
          e.preventDefault()
          if (video.paused) void video.play()
          else video.pause()
        }
      }
    }

    const onKeyUp = (e: KeyboardEvent) => {
      if (e.key !== 'ArrowRight') return
      if (isBlockedTarget(e.target)) return

      e.preventDefault()
      e.stopImmediatePropagation()

      const wasHolding = rightKeyDownRef.current
      rightKeyDownRef.current = false
      clearHoldTimer()

      if (fastForwardRef.current) {
        stopFastForward()
      } else if (wasHolding) {
        video.currentTime = Math.min(
          video.duration || Infinity,
          video.currentTime + SEEK_STEP,
        )
      }
    }

    const onPlay = () => requestAnimationFrame(focusContainer)

    video.addEventListener('play', onPlay)
    window.addEventListener('keydown', onKeyDown, true)
    window.addEventListener('keyup', onKeyUp, true)

    return () => {
      video.removeEventListener('timeupdate', onTick)
      video.removeEventListener('play', onPlay)
      window.removeEventListener('keydown', onKeyDown, true)
      window.removeEventListener('keyup', onKeyUp, true)
      clearHoldTimer()
      rightKeyDownRef.current = false
      fastForwardRef.current = false
      video.playbackRate = 1
    }
  }, [src, focusContainer])

  if (!src) {
    return (
      <div className="flex h-[min(38vh,320px)] items-center justify-center rounded-lg border border-dashed border-[var(--sv-border)] bg-[var(--sv-canvas)] text-[var(--sv-fg-muted)]">
        上传或选择历史记录后播放视频
      </div>
    )
  }

  return (
    <div
      ref={containerRef}
      tabIndex={0}
      className="rounded-lg border border-[var(--sv-border)] bg-black outline-none focus-visible:ring-2 focus-visible:ring-[var(--sv-accent)]"
      onPointerUpCapture={() => {
        // 点击原生播放/进度条后，焦点会留在控件上导致方向键失效；松手后收回焦点
        requestAnimationFrame(focusContainer)
      }}
      title="→ 短按快进 10 秒，长按 2 倍速"
    >
      <video
        key={src}
        ref={videoRef}
        src={src}
        controls
        playsInline
        preload="metadata"
        className="h-[min(38vh,320px)] w-full bg-black object-contain"
      />
    </div>
  )
})
