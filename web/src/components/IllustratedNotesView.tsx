import { useState } from 'react'
import { resolveSectionThumbUrl } from '../lib/api'
import { groupTranscriptBySections, formatTime } from '../lib/transcript'
import { TranscriptSegmentRow } from './TranscriptSegmentRow'
import type { NoteSection, SectionFrame, TranscriptSegment } from '../types'

interface Props {
  sections: NoteSection[]
  activeIndex: number
  onSectionSelect: (section: NoteSection, index: number) => void
  transcript?: string | null
  transcriptSegments?: TranscriptSegment[] | null
  onTranscriptSeek?: (time: number) => void
  frameStatus?: string
  frameProgressDone?: number
  frameProgressTotal?: number
  frameErrorMessage?: string | null
  onRetryFrames?: () => void
}

function hasAnyFrames(sections: NoteSection[]): boolean {
  return sections.some(
    (s) => Boolean(s.frames?.length) || Boolean(s.thumbnail),
  )
}

type BlockItem =
  | { kind: 'frame'; frame: SectionFrame }
  | { kind: 'segment'; segment: TranscriptSegment }

export function IllustratedNotesView({
  sections,
  activeIndex,
  onSectionSelect,
  transcript,
  transcriptSegments,
  onTranscriptSeek,
  frameStatus,
  frameProgressDone = 0,
  frameProgressTotal = 0,
  frameErrorMessage,
  onRetryFrames,
}: Props) {
  const segments = transcriptSegments ?? []
  const hasSegments = segments.length > 0
  const framesExist = hasAnyFrames(sections)

  const frameBanner = (() => {
    if (frameStatus === 'processing') {
      const total = frameProgressTotal > 0 ? frameProgressTotal : '…'
      return (
        <p className="rounded-lg border border-[var(--sv-border)] bg-[var(--sv-canvas-subtle)] px-3 py-2 text-sm text-[var(--sv-fg-muted)]">
          配图生成中 {frameProgressDone}/{total}…
        </p>
      )
    }
    if (frameStatus === 'error') {
      return (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-[var(--sv-danger-fg)]/30 bg-[var(--sv-danger-bg)] px-3 py-2 text-sm text-[var(--sv-danger-fg)]">
          <span className="flex-1">
            配图生成失败{frameErrorMessage ? `：${frameErrorMessage}` : ''}
          </span>
          {onRetryFrames && (
            <button
              type="button"
              className="rounded-md bg-[var(--sv-accent)] px-2 py-1 text-xs text-[var(--sv-accent-fg)]"
              onClick={onRetryFrames}
            >
              重新生成配图
            </button>
          )}
        </div>
      )
    }
    if (!framesExist && frameStatus === 'pending' && onRetryFrames) {
      return (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-[var(--sv-border)] bg-[var(--sv-canvas-subtle)] px-3 py-2 text-sm text-[var(--sv-fg-muted)]">
          <span className="flex-1">尚未生成配图，可手动触发</span>
          <button
            type="button"
            className="rounded-md border border-[var(--sv-border)] px-2 py-1 text-xs hover:bg-[var(--sv-canvas)]"
            onClick={onRetryFrames}
          >
            生成配图
          </button>
        </div>
      )
    }
    if (frameStatus === 'skipped') {
      return (
        <p className="text-xs text-[var(--sv-fg-muted)]">无本地视频文件，已跳过配图</p>
      )
    }
    return null
  })()

  if (!transcript && !hasSegments) {
    return <p className="text-sm text-[var(--sv-fg-muted)]">处理完成后显示图文笔记</p>
  }

  if (!hasSegments) {
    return (
      <div className="space-y-6 text-sm leading-relaxed text-[var(--sv-fg)]">
        {frameBanner}
        {sections.map((sec, i) => (
          <SectionBlock
            key={`${sec.start_time}-${i}`}
            section={sec}
            sectionIndex={i}
            active={i === activeIndex}
            items={interleaveFramesAndSegments(sectionFrames(sec), [])}
            onSectionSelect={onSectionSelect}
            onTranscriptSeek={onTranscriptSeek}
          />
        ))}
        <pre className="select-text cursor-text whitespace-pre-wrap text-[var(--sv-fg-muted)]">
          {transcript}
        </pre>
      </div>
    )
  }

  const groups = groupTranscriptBySections(segments, sections)

  return (
    <div className="space-y-8 text-sm leading-relaxed text-[var(--sv-fg)]">
      {frameBanner}
      {groups.map((group) => {
        const sectionIndex = group.sectionIndex
        if (sectionIndex < 0) return null
        const sec = sections[sectionIndex]
        const active = sectionIndex === activeIndex
        const frames = sectionFrames(sec)
        if (group.items.length === 0 && frames.length === 0) return null
        return (
          <SectionBlock
            key={`${group.title}-${group.start_time}-${sectionIndex}`}
            section={sec}
            sectionIndex={sectionIndex}
            active={active}
            items={interleaveFramesAndSegments(frames, group.items)}
            onSectionSelect={onSectionSelect}
            onTranscriptSeek={onTranscriptSeek}
          />
        )
      })}
    </div>
  )
}

function sectionFrames(section: NoteSection): SectionFrame[] {
  if (section.frames?.length) {
    return [...section.frames].sort((a, b) => a.time - b.time)
  }
  const thumb = resolveSectionThumbUrl(section.thumbnail)
  if (thumb) {
    return [{ time: section.start_time, url: section.thumbnail! }]
  }
  return []
}

function interleaveFramesAndSegments(
  frames: SectionFrame[],
  segments: TranscriptSegment[],
): BlockItem[] {
  type TimelineEntry =
    | { kind: 'frame'; time: number; frame: SectionFrame }
    | { kind: 'segment'; time: number; segment: TranscriptSegment }

  const timeline: TimelineEntry[] = []
  for (const frame of frames) {
    timeline.push({ kind: 'frame', time: frame.time, frame })
  }
  for (const segment of segments) {
    timeline.push({ kind: 'segment', time: segment.start_time, segment })
  }
  timeline.sort((a, b) => {
    if (a.time !== b.time) return a.time - b.time
    return a.kind === 'frame' ? -1 : 1
  })
  return timeline as BlockItem[]
}

function SectionBlock({
  section,
  sectionIndex,
  active,
  items,
  onSectionSelect,
  onTranscriptSeek,
}: {
  section: NoteSection
  sectionIndex: number
  active: boolean
  items: BlockItem[]
  onSectionSelect: (section: NoteSection, index: number) => void
  onTranscriptSeek?: (time: number) => void
}) {
  const handleHeaderClick = () => {
    if (sectionIndex >= 0) onSectionSelect(section, sectionIndex)
    else onTranscriptSeek?.(section.start_time)
  }

  return (
    <article
      className={`rounded-lg border px-3 py-3 transition ${
        active
          ? 'border-[var(--sv-accent)] bg-[var(--sv-canvas-subtle)] ring-1 ring-[var(--sv-accent)]'
          : 'border-[var(--sv-border)] bg-[var(--sv-canvas)]'
      }`}
    >
      <button
        type="button"
        onClick={handleHeaderClick}
        className="mb-2 flex w-full items-center gap-2 text-left hover:text-[var(--sv-accent)]"
        title="跳转到该段视频位置"
      >
        <span className="shrink-0 font-mono text-xs text-[var(--sv-fg-muted)]">
          {formatTime(section.start_time)}
        </span>
        <span className="font-medium text-[var(--sv-fg)] underline-offset-2 hover:underline">
          {section.title}
        </span>
        {section.frames && section.frames.length > 1 && (
          <span className="text-xs font-normal text-[var(--sv-fg-muted)]">
            · {section.frames.length} 图
          </span>
        )}
      </button>

      {items.length > 0 ? (
        <div className="select-text cursor-text space-y-0.5 text-[var(--sv-fg)]">
          {items.map((item, i) =>
            item.kind === 'frame' ? (
              <div key={`f-${item.frame.time}-${i}`} className="my-2 first:mt-0 last:mb-0">
                <FrameThumbnail
                  frame={item.frame}
                  alt={section.title}
                  onClick={() => onTranscriptSeek?.(item.frame.time)}
                />
              </div>
            ) : (
              <TranscriptSegmentRow
                key={`s-${item.segment.start_time}-${i}`}
                segment={item.segment}
                onSeek={onTranscriptSeek}
              />
            ),
          )}
        </div>
      ) : (
        <p className="text-xs text-[var(--sv-fg-muted)]">（本节无转写句段）</p>
      )}
    </article>
  )
}

function FrameThumbnail({
  frame,
  alt,
  onClick,
}: {
  frame: SectionFrame
  alt: string
  onClick: () => void
}) {
  const [failed, setFailed] = useState(false)
  const src = resolveSectionThumbUrl(frame.url)
  if (!src || failed) return null
  return (
    <button
      type="button"
      onClick={onClick}
      className="block w-full overflow-hidden rounded-md"
      title={`跳转到 ${formatTime(frame.time)}`}
    >
      <img
        src={src}
        alt={alt}
        className="max-h-48 w-full object-contain"
        loading="lazy"
        onError={() => setFailed(true)}
      />
      <span className="mt-1 block text-center font-mono text-[10px] text-[var(--sv-fg-muted)]">
        {formatTime(frame.time)}
      </span>
    </button>
  )
}
