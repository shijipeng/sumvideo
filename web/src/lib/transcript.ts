import type { NoteSection, TranscriptSegment } from '../types'

export interface TranscriptGroup {
  title: string
  start_time: number
  /** 对应 sections 中的索引；-1 表示无对应章节（不应出现） */
  sectionIndex: number
  items: TranscriptSegment[]
}

function _sectionEnd(sec: NoteSection, isLast: boolean): number {
  const end = sec.end_time ?? Number.POSITIVE_INFINITY
  return isLast ? end + 2.0 : end + 0.3
}

function _pickSectionForSegment(
  seg: TranscriptSegment,
  sections: NoteSection[],
): number {
  const t = seg.start_time
  for (let i = 0; i < sections.length; i++) {
    const sec = sections[i]
    const end = _sectionEnd(sec, i === sections.length - 1)
    if (t >= sec.start_time - 0.3 && t < end) {
      return i
    }
  }
  let best = 0
  let bestDist = Number.POSITIVE_INFINITY
  for (let i = 0; i < sections.length; i++) {
    const sec = sections[i]
    const mid = (sec.start_time + (sec.end_time ?? sec.start_time)) / 2
    const dist = Math.abs(t - mid)
    if (dist < bestDist) {
      bestDist = dist
      best = i
    }
  }
  return best
}

/** 按笔记章节时间范围聚合 Whisper 转写句段（无「其他」分组） */
export function groupTranscriptBySections(
  segments: TranscriptSegment[],
  sections: NoteSection[],
): TranscriptGroup[] {
  if (!segments.length) return []

  if (!sections.length) {
    return [
      {
        title: '转写',
        start_time: segments[0]?.start_time ?? 0,
        sectionIndex: -1,
        items: segments,
      },
    ]
  }

  const buckets: TranscriptSegment[][] = sections.map(() => [])

  for (const seg of segments) {
    const idx = _pickSectionForSegment(seg, sections)
    buckets[idx].push(seg)
  }

  return sections.map((sec, i) => ({
    title: sec.title,
    start_time: sec.start_time,
    sectionIndex: i,
    items: buckets[i],
  }))
}

export function formatTime(sec: number) {
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}
