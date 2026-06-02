import { sectionHasBody, SectionBody } from '../lib/sectionRender'
import { groupTranscriptBySections, formatTime } from '../lib/transcript'
import { TranscriptSegmentRow } from './TranscriptSegmentRow'
import type { NoteSection, TranscriptSegment } from '../types'

interface Props {
  overview?: string | null
  sections: NoteSection[]
  activeIndex: number
  onSectionSelect: (section: NoteSection, index: number) => void
  transcript?: string | null
  transcriptSegments?: TranscriptSegment[] | null
  onTranscriptSeek?: (time: number) => void
  legacySummary?: string | null
  /** 如「编程 · 口播讲解」 */
  metaLabel?: string | null
}

export function NotesView({
  overview,
  sections,
  activeIndex,
  onSectionSelect,
  transcript,
  transcriptSegments,
  onTranscriptSeek,
  legacySummary,
  metaLabel,
}: Props) {
  const hasStructured = Boolean(
    overview || sections.some((s) => sectionHasBody(s)),
  )

  if (!hasStructured && !legacySummary && !transcript) {
    return <p className="text-sm text-[var(--sv-fg-muted)]">处理完成后显示 AI 笔记</p>
  }

  if (!hasStructured && legacySummary) {
    return (
      <div className="space-y-4 text-sm leading-relaxed text-[var(--sv-fg)]">
        <div className="whitespace-pre-wrap">{legacySummary}</div>
        {sections.length > 0 && (
          <SectionNotesBlock
            sections={sections}
            activeIndex={activeIndex}
            onSectionSelect={onSectionSelect}
          />
        )}
        {transcript && (
          <TranscriptBlock
            transcript={transcript}
            transcriptSegments={transcriptSegments}
            sections={sections}
            onSeek={onTranscriptSeek}
          />
        )}
      </div>
    )
  }

  return (
    <div className="space-y-5 text-sm leading-relaxed text-[var(--sv-fg)]">
      {overview && (
        <section>
          {metaLabel && (
            <p className="mb-2 text-xs text-[var(--sv-fg-muted)]">{metaLabel}</p>
          )}
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-[var(--sv-fg-muted)]">
            概述
          </h3>
          <p className="select-text cursor-text text-[var(--sv-fg)]">{overview}</p>
        </section>
      )}

      {sections.length > 0 && (
        <SectionNotesBlock
          sections={sections}
          activeIndex={activeIndex}
          onSectionSelect={onSectionSelect}
        />
      )}

      {transcript && (
        <TranscriptBlock
          transcript={transcript}
          transcriptSegments={transcriptSegments}
          sections={sections}
          onSeek={onTranscriptSeek}
        />
      )}
    </div>
  )
}

function SectionNotesBlock({
  sections,
  activeIndex,
  onSectionSelect,
}: {
  sections: NoteSection[]
  activeIndex: number
  onSectionSelect: (section: NoteSection, index: number) => void
}) {
  return (
    <details open className="group/notes">
      <summary className="mb-2 flex cursor-pointer list-none items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-[var(--sv-fg-muted)] [&::-webkit-details-marker]:hidden">
        <span
          aria-hidden
          className="text-[10px] transition-transform group-open/notes:rotate-90"
        >
          ▶
        </span>
        分段笔记
        <span className="font-normal normal-case tracking-normal">（{sections.length} 段）</span>
      </summary>
      <SectionList
        sections={sections}
        activeIndex={activeIndex}
        onSectionSelect={onSectionSelect}
      />
    </details>
  )
}

function SectionList({
  sections,
  activeIndex,
  onSectionSelect,
}: {
  sections: NoteSection[]
  activeIndex: number
  onSectionSelect: (section: NoteSection, index: number) => void
}) {
  return (
    <ul className="space-y-3">
      {sections.map((sec, i) => {
        const active = i === activeIndex
        return (
          <li
            key={`${sec.start_time}-${i}`}
            className={`rounded-lg border px-3 py-3 transition ${
              active
                ? 'border-[var(--sv-accent)] bg-[var(--sv-canvas-subtle)] ring-1 ring-[var(--sv-accent)]'
                : 'border-[var(--sv-border)] bg-[var(--sv-canvas)]'
            }`}
          >
            <button
              type="button"
              onClick={() => onSectionSelect(sec, i)}
              className="mb-1.5 flex w-full items-center gap-2 text-left hover:text-[var(--sv-accent)]"
              title="跳转到该段视频位置"
            >
              <span className="shrink-0 font-mono text-xs text-[var(--sv-fg-muted)]">
                {formatTime(sec.start_time)}
              </span>
              <span className="font-medium text-[var(--sv-fg)] underline-offset-2 hover:underline">
                {sec.title}
              </span>
            </button>
            <div className="select-text cursor-text">
              <SectionBody section={sec} />
            </div>
          </li>
        )
      })}
    </ul>
  )
}

function TranscriptBlock({
  transcript,
  transcriptSegments,
  sections,
  onSeek,
}: {
  transcript: string
  transcriptSegments?: TranscriptSegment[] | null
  sections: NoteSection[]
  onSeek?: (time: number) => void
}) {
  const segments = transcriptSegments ?? []
  const hasSegments = segments.length > 0
  const groups = hasSegments ? groupTranscriptBySections(segments, sections) : []

  return (
    <details className="rounded-lg border border-[var(--sv-border)] bg-[var(--sv-canvas)]">
      <summary className="cursor-pointer px-3 py-2 text-[var(--sv-fg-muted)]">
        查看完整转写文本
        {hasSegments && (
          <span className="ml-2 text-xs text-[var(--sv-fg-muted)]">
            （{sections.length ? '按章节 · 逐句' : '逐句'}，点击跳转）
          </span>
        )}
      </summary>

      {hasSegments ? (
        <div className="space-y-2 px-3 pb-2">
          {groups.map((group, gi) => (
            <div key={`${group.title}-${gi}`}>
              {sections.length > 0 && (
                <button
                  type="button"
                  onClick={() => onSeek?.(group.start_time)}
                  className="mb-1 flex items-center gap-2 text-left text-xs font-semibold text-[var(--sv-fg)] hover:text-[var(--sv-accent)]"
                >
                  <span className="font-mono text-[var(--sv-fg-muted)]">
                    {formatTime(group.start_time)}
                  </span>
                  {group.title}
                </button>
              )}
              <ul className="space-y-0.5">
                {group.items.map((seg, si) => (
                  <li key={`${seg.start_time}-${si}`}>
                    <TranscriptSegmentRow segment={seg} onSeek={onSeek} />
                  </li>
                ))}
              </ul>
              {group.items.length === 0 && (
                <p className="text-xs text-[var(--sv-fg-muted)]">（本节无转写句段）</p>
              )}
            </div>
          ))}
        </div>
      ) : (
        <pre className="whitespace-pre-wrap px-3 pb-2 text-xs leading-snug text-[var(--sv-fg-muted)]">
          {transcript}
        </pre>
      )}
    </details>
  )
}
