import type { FormEvent } from 'react'

interface Props {
  onImport: (url: string) => void
  disabled?: boolean
  importing?: boolean
}

export function ImportUrlField({ onImport, disabled, importing }: Props) {
  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const form = e.currentTarget
    const input = form.elements.namedItem('video-url') as HTMLInputElement
    const url = input.value.trim()
    if (!url) return
    onImport(url)
    input.value = ''
  }

  return (
    <form onSubmit={handleSubmit} className="flex min-w-0 flex-1 items-center gap-1.5">
      <input
        id="video-url"
        name="video-url"
        type="url"
        placeholder="粘贴视频链接"
        disabled={disabled || importing}
        className="min-w-0 flex-1 rounded-lg border border-[var(--sv-border)] bg-[var(--sv-bg)] px-2.5 py-1.5 text-sm text-[var(--sv-fg)] placeholder:text-[var(--sv-fg-muted)] disabled:opacity-50"
      />
      <button
        type="submit"
        disabled={disabled || importing}
        className="shrink-0 rounded-lg border border-[var(--sv-border)] px-3 py-1.5 text-sm text-[var(--sv-fg)] hover:bg-[var(--sv-canvas-subtle)] disabled:opacity-50"
      >
        {importing ? '导入中…' : '导入'}
      </button>
    </form>
  )
}
