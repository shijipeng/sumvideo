import type { Chapter } from '../types'

function formatTime(sec: number) {
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

interface Props {
  chapters: Chapter[]
  activeIndex: number
  onSelect: (chapter: Chapter, index: number) => void
}

export function ChapterList({ chapters, activeIndex, onSelect }: Props) {
  if (!chapters.length) {
    return <p className="text-sm text-zinc-500">暂无章节，处理完成后显示</p>
  }

  return (
    <ul className="space-y-1">
      {chapters.map((ch, i) => (
        <li key={`${ch.start_time}-${i}`}>
          <button
            type="button"
            onClick={() => onSelect(ch, i)}
            className={`w-full rounded-lg px-3 py-2 text-left text-sm transition ${
              i === activeIndex
                ? 'bg-indigo-600/30 text-indigo-200 ring-1 ring-indigo-500/50'
                : 'text-zinc-300 hover:bg-zinc-800'
            }`}
          >
            <span className="mr-2 font-mono text-xs text-zinc-500">{formatTime(ch.start_time)}</span>
            {ch.title}
          </button>
        </li>
      ))}
    </ul>
  )
}
