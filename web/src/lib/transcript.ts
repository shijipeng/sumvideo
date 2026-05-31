import type { NoteSection, TranscriptSegment } from '../types'

export interface TranscriptGroup {
  title: string
  start_time: number
  items: TranscriptSegment[]
}

export interface MergeTranscriptOptions {
  maxChars?: number
  maxDurationSec?: number
  maxGapSec?: number
}

const DEFAULT_MERGE_OPTS: Required<MergeTranscriptOptions> = {
  maxChars: 120,
  maxDurationSec: 45,
  maxGapSec: 2,
}

/** 展示层合并相邻句段为自然段（不影响存储） */
export function mergeTranscriptSegments(
  segments: TranscriptSegment[],
  opts?: MergeTranscriptOptions,
): TranscriptSegment[] {
  if (!segments.length) return []

  const { maxChars, maxDurationSec, maxGapSec } = { ...DEFAULT_MERGE_OPTS, ...opts }
  const sorted = [...segments].sort((a, b) => a.start_time - b.start_time)
  const result: TranscriptSegment[] = []

  let current: TranscriptSegment = { ...sorted[0] }

  for (let i = 1; i < sorted.length; i++) {
    const next = sorted[i]
    const gap = next.start_time - current.end_time
    const mergedText = current.text + next.text
    const mergedDuration = next.end_time - current.start_time

    if (gap <= maxGapSec && mergedText.length <= maxChars && mergedDuration <= maxDurationSec) {
      current = {
        start_time: current.start_time,
        end_time: Math.max(current.end_time, next.end_time),
        text: mergedText,
      }
    } else {
      result.push(current)
      current = { ...next }
    }
  }

  result.push(current)
  return result
}

/** 按笔记章节时间范围聚合 Whisper 转写句段 */
export function groupTranscriptBySections(
  segments: TranscriptSegment[],
  sections: NoteSection[],
): TranscriptGroup[] {
  if (!segments.length) return []

  if (!sections.length) {
    return [{ title: '转写', start_time: segments[0]?.start_time ?? 0, items: segments }]
  }

  const assigned = new Set<number>()
  const groups: TranscriptGroup[] = []

  for (const sec of sections) {
    const end = sec.end_time ?? Number.POSITIVE_INFINITY
    const items: TranscriptSegment[] = []
    segments.forEach((s, idx) => {
      if (assigned.has(idx)) return
      if (s.start_time >= sec.start_time - 0.2 && s.start_time < end + 0.2) {
        items.push(s)
        assigned.add(idx)
      }
    })
    groups.push({ title: sec.title, start_time: sec.start_time, items })
  }

  const orphan = segments.filter((_, idx) => !assigned.has(idx))
  if (orphan.length) {
    groups.push({ title: '其他', start_time: orphan[0].start_time, items: orphan })
  }

  return groups
}

export function formatTime(sec: number) {
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}
