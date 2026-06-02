import { stripNoteLabel } from '../lib/noteText'
import type { NoteSection } from '../types'

export function sectionHasBody(sec: NoteSection): boolean {
  return Boolean(
    sec.lead ||
      sec.content ||
      (sec.points && sec.points.length > 0) ||
      (sec.steps && sec.steps.length > 0) ||
      (sec.qa && sec.qa.length > 0),
  )
}

export function SectionBody({ section }: { section: NoteSection }) {
  const fmt = section.format ?? (section.content ? 'prose' : section.steps ? 'steps' : section.qa ? 'qa' : 'bullets')

  return (
    <div className="select-text cursor-text">
      {section.lead && (
        <p className="mb-1.5 text-[var(--sv-fg)]">{stripNoteLabel(section.lead)}</p>
      )}
      {fmt === 'prose' && section.content && (
        <p className="whitespace-pre-wrap text-[var(--sv-fg)]">{stripNoteLabel(section.content)}</p>
      )}
      {fmt === 'steps' && section.steps && section.steps.length > 0 && (
        <ol className="mt-1 list-inside list-decimal space-y-1 text-[var(--sv-fg-muted)]">
          {section.steps.map((step, j) => (
            <li key={j}>{stripNoteLabel(step)}</li>
          ))}
        </ol>
      )}
      {fmt === 'qa' && section.qa && section.qa.length > 0 && (
        <dl className="mt-1 space-y-2 text-[var(--sv-fg-muted)]">
          {section.qa.map((pair, j) => (
            <div key={j}>
              {pair.q && (
                <dt className="font-medium text-[var(--sv-fg)]">问：{stripNoteLabel(pair.q)}</dt>
              )}
              {pair.a && <dd className="mt-0.5 pl-2">答：{stripNoteLabel(pair.a)}</dd>}
            </div>
          ))}
        </dl>
      )}
      {(fmt === 'bullets' || (!section.content && !section.steps && !section.qa)) &&
        section.points &&
        section.points.length > 0 && (
          <ul className="mt-1 list-inside list-disc space-y-1 text-[var(--sv-fg-muted)]">
            {section.points.map((p, j) => (
              <li key={j}>{stripNoteLabel(p)}</li>
            ))}
          </ul>
        )}
    </div>
  )
}
