import ReactMarkdown from 'react-markdown'

interface Props {
  summary: string | null | undefined
  transcript?: string | null
}

export function SummaryView({ summary, transcript }: Props) {
  if (!summary && !transcript) {
    return <p className="text-sm text-zinc-500">处理完成后显示 AI 总结</p>
  }

  return (
    <div className="space-y-4 text-sm leading-relaxed text-zinc-300">
      {summary && (
        <div className="prose prose-invert max-w-none prose-headings:text-zinc-100 prose-p:text-zinc-300">
          <ReactMarkdown>{summary}</ReactMarkdown>
        </div>
      )}
      {transcript && (
        <details className="rounded-lg border border-zinc-800 bg-zinc-900/50">
          <summary className="cursor-pointer px-3 py-2 text-zinc-400">查看完整转写文本</summary>
          <pre className="max-h-48 overflow-auto whitespace-pre-wrap px-3 pb-3 text-xs text-zinc-500">
            {transcript}
          </pre>
        </details>
      )}
    </div>
  )
}
