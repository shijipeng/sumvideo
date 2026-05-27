import type { WhisperModelOption } from '../types'

interface Props {
  options: WhisperModelOption[]
  value: string
  onChange: (id: string) => void
  platformLabel: string
}

export function WhisperModelSelect({ options, value, onChange, platformLabel }: Props) {
  const groups = Array.from(new Set(options.map((o) => o.group)))

  return (
    <div>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2.5 text-sm text-zinc-200 focus:border-indigo-500 focus:outline-none"
      >
        {groups.map((group) => (
          <optgroup key={group} label={group}>
            {options
              .filter((o) => o.group === group)
              .map((o) => (
                <option key={o.id} value={o.id} disabled={!o.supported_on_current_platform}>
                  {o.label}
                  {o.recommended ? ' ★本机推荐' : ''}
                  {!o.supported_on_current_platform ? '（不适用当前系统）' : ''}
                  {o.platform_hint ? ` · ${o.platform_hint}` : ''}
                </option>
              ))}
          </optgroup>
        ))}
      </select>
      <p className="mt-1 text-xs text-zinc-500">
        当前系统：<span className="text-zinc-400">{platformLabel}</span>
        。Mac M 系列请选 MLX；Windows 请选 faster-whisper。首次使用会下载模型。
      </p>
    </div>
  )
}
