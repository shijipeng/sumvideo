import { useMemo, useState } from 'react'
import type { HistoryItem } from '../types'

export type HistorySortKey = 'time' | 'name'
export type HistorySortOrder = 'desc' | 'asc'

interface Props {
  items: HistoryItem[]
  selectedId: string | null
  onSelect: (id: string) => void
  onDelete: (id: string) => void
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    pending: '等待中',
    processing: '处理中',
    done: '已完成',
    error: '失败',
  }
  return map[status] ?? status
}

function sortHistory(
  items: HistoryItem[],
  key: HistorySortKey,
  order: HistorySortOrder,
): HistoryItem[] {
  const sorted = [...items]
  sorted.sort((a, b) => {
    let cmp = 0
    if (key === 'time') {
      const ta = a.created_at || ''
      const tb = b.created_at || ''
      cmp = ta.localeCompare(tb)
    } else {
      cmp = a.filename.localeCompare(b.filename, 'zh-CN', { sensitivity: 'base' })
    }
    if (cmp === 0) cmp = a.id.localeCompare(b.id)
    return order === 'asc' ? cmp : -cmp
  })
  return sorted
}

export function HistoryPanel({ items, selectedId, onSelect, onDelete }: Props) {
  const [sortKey, setSortKey] = useState<HistorySortKey>('time')
  const [sortOrder, setSortOrder] = useState<HistorySortOrder>('desc')

  const sortedItems = useMemo(
    () => sortHistory(items, sortKey, sortOrder),
    [items, sortKey, sortOrder],
  )

  if (!items.length) {
    return <p className="text-sm text-[var(--sv-fg-muted)]">暂无历史记录</p>
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2">
      <div className="flex shrink-0 flex-wrap items-center gap-1.5">
        <label className="sr-only" htmlFor="history-sort">
          排序
        </label>
        <select
          id="history-sort"
          value={`${sortKey}-${sortOrder}`}
          onChange={(e) => {
            const [k, o] = e.target.value.split('-') as [HistorySortKey, HistorySortOrder]
            setSortKey(k)
            setSortOrder(o)
          }}
          className="min-w-0 flex-1 rounded-md border border-[var(--sv-border)] bg-[var(--sv-bg)] px-2 py-1 text-xs text-[var(--sv-fg)]"
        >
          <option value="time-desc">时间 · 新→旧</option>
          <option value="time-asc">时间 · 旧→新</option>
          <option value="name-asc">名称 · A→Z</option>
          <option value="name-desc">名称 · Z→A</option>
        </select>
      </div>

      <ul className="min-h-0 flex-1 space-y-1 overflow-y-auto">
        {sortedItems.map((item) => (
          <li
            key={item.id}
            className={`group flex items-center gap-1 rounded-lg px-2 py-2 text-sm ${
              selectedId === item.id
                ? 'bg-[var(--sv-canvas-subtle)]'
                : 'hover:bg-[var(--sv-canvas)]'
            }`}
          >
            <button
              type="button"
              className="min-w-0 flex-1 truncate text-left text-[var(--sv-fg)]"
              onClick={() => onSelect(item.id)}
              title={item.filename}
            >
              <div className="truncate font-medium">{item.filename}</div>
              <div className="text-xs text-[var(--sv-fg-muted)]">
                {statusLabel(item.status)}
                {item.status === 'processing' && ` ${Math.round(item.progress)}%`}
              </div>
            </button>
            <button
              type="button"
              className="shrink-0 rounded px-1.5 py-0.5 text-xs text-[var(--sv-fg-muted)] opacity-0 hover:bg-[var(--sv-danger-bg)] hover:text-[var(--sv-danger-fg)] group-hover:opacity-100"
              onClick={(e) => {
                e.stopPropagation()
                if (confirm('确定删除这条记录？')) onDelete(item.id)
              }}
            >
              删
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
