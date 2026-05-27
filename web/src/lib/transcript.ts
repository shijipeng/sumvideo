import type { NoteSection, TranscriptSegment } from '../types'

export interface TranscriptGroup {
  title: string
  start_time: number
  items: TranscriptSegment[]
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
