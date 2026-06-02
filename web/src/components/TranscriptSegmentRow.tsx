import { formatTime } from '../lib/transcript'
import type { TranscriptSegment } from '../types'

interface Props {
  segment: TranscriptSegment
  onSeek?: (time: number) => void
}

export function TranscriptSegmentRow({ segment, onSeek }: Props) {
  return (
    <button
      type="button"
      onClick={() => onSeek?.(segment.start_time)}
      className="w-full rounded border border-transparent px-1 py-0.5 text-left hover:border-[var(--sv-border)] hover:bg-[var(--sv-canvas-subtle)]"
    >
      <span className="mr-1.5 font-mono text-[10px] leading-snug text-[var(--sv-fg-muted)]">
        {formatTime(segment.start_time)}
      </span>
      <span className="text-xs leading-snug text-[var(--sv-fg-muted)]">
        {segment.text}
      </span>
    </button>
  )
}
