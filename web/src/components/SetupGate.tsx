import { useEffect, useState } from 'react'
import { getSettings, saveSettings } from '../lib/api'
import { WhisperModelSelect } from './WhisperModelSelect'
import type { AppSettings, ModelOption } from '../types'

interface Props {
  /** 设置保存成功（之后进入模型下载或主界面） */
  onSaved: () => void | Promise<void>
  /** 从主界面进入时为 true，允许不重复填写 API Key */
  isUpdate?: boolean
}

export function SetupGate({ onSaved, isUpdate = false }: Props) {
  const [options, setOptions] = useState<AppSettings | null>(null)
  const [apiKey, setApiKey] = useState('')
  const [savedMask, setSavedMask] = useState('')
  const [apiKeyDirty, setApiKeyDirty] = useState(false)
  const [whisperModel, setWhisperModel] = useState('')
  const [deepseekModel, setDeepseekModel] = useState('deepseek-v4-flash')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getSettings()
      .then((s) => {
        setOptions(s)
        if (s.whisper_model) setWhisperModel(s.whisper_model)
        else if (s.recommended_whisper_model) setWhisperModel(s.recommended_whisper_model)
        if (s.deepseek_model) setDeepseekModel(s.deepseek_model)
        else if (s.deepseek_options[0]) setDeepseekModel(s.deepseek_options[0].id)

        if (s.api_key_invalid) {
          setError(
            '已保存的 API Key 无效（例如误填了网址）。请重新填写以 sk- 开头的 DeepSeek 密钥。',
          )
          setApiKey('')
          setSavedMask('')
          setApiKeyDirty(true)
        } else if (s.api_key_masked) {
          setSavedMask(s.api_key_masked)
          setApiKey(s.api_key_masked)
          setApiKeyDirty(false)
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : '加载失败'))
  }, [])

  useEffect(() => {
    if (options && !whisperModel) {
      const rec =
        options.whisper_options.find((o) => o.recommended && o.supported_on_current_platform)
          ?.id ?? options.recommended_whisper_model
      if (rec) setWhisperModel(rec)
    }
  }, [options, whisperModel])

  const handleApiKeyChange = (value: string) => {
    setApiKeyDirty(true)
    setApiKey(value)
    if (error?.includes('API Key')) setError(null)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    const needsNewKey = !options?.api_configured || options.api_key_invalid
    const keepingSaved =
      !apiKeyDirty && savedMask && apiKey === savedMask && options?.api_configured

    if (needsNewKey && !apiKey.trim()) {
      setError('请填写 DeepSeek API Key')
      return
    }
    if (!keepingSaved && apiKey.trim() && apiKey.includes('•')) {
      setError('请填写完整的新 API Key，不要只保留掩码占位符')
      return
    }
    if (!whisperModel) {
      setError('请选择 Whisper 转写模型')
      return
    }

    setSaving(true)
    try {
      const payload: {
        whisper_model: string
        deepseek_model: string
        api_key?: string
      } = {
        whisper_model: whisperModel,
        deepseek_model: deepseekModel,
      }

      if (keepingSaved) {
        // 未改动：后端保留已缓存的 Key
      } else if (apiKey.trim()) {
        payload.api_key = apiKey.trim()
      } else if (!needsNewKey) {
        // 更新设置且 Key 留空：保留
      } else {
        setError('请填写 DeepSeek API Key')
        setSaving(false)
        return
      }

      await saveSettings(payload)
      if (payload.api_key) {
        const newMask =
          payload.api_key.length > 7
            ? `${payload.api_key.slice(0, 3)}${'•'.repeat(12)}${payload.api_key.slice(-4)}`
            : 'sk-••••••••'
        setSavedMask(newMask)
        setApiKey(newMask)
        setApiKeyDirty(false)
      } else if (keepingSaved) {
        setApiKey(savedMask)
        setApiKeyDirty(false)
      }
      await onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  if (!options) {
    return (
      <div className="flex min-h-dvh flex-1 items-center justify-center bg-[var(--sv-bg)] text-[var(--sv-fg-muted)]">
        加载配置...
      </div>
    )
  }

  const hasStoredKey = options.api_configured && savedMask && !apiKeyDirty

  return (
    <div className="flex min-h-dvh flex-1 flex-col items-center justify-center bg-[var(--sv-bg)] px-4">
      <div className="w-full max-w-lg rounded-2xl border border-[var(--sv-border)] bg-[var(--sv-canvas)] p-8 shadow-xl">
        <h1 className="text-2xl font-semibold text-[var(--sv-fg)]">
          {isUpdate ? '模型与 API 设置' : 'SumVideo 初始设置'}
        </h1>
        <p className="mt-2 text-sm text-[var(--sv-fg-muted)]">
          {isUpdate
            ? 'API Key 已保存在本机。不修改则保持原密钥；要更换请清空后输入新的 sk- 密钥。'
            : '请先配置 API 并选择转写模型，保存后将引导下载所选模型。'}
        </p>

        <form onSubmit={handleSubmit} className="mt-8 space-y-6">
          <Field label="DeepSeek API Key" required={!options.api_configured}>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => handleApiKeyChange(e.target.value)}
              onFocus={() => {
                if (hasStoredKey && apiKey === savedMask) {
                  setApiKey('')
                  setApiKeyDirty(true)
                }
              }}
              placeholder={options.api_configured ? '已配置（掩码显示）' : 'sk-...'}
              className={inputClass}
              autoComplete="off"
            />
            {hasStoredKey && (
              <p className="mt-1 text-xs text-emerald-500/90">
                已保存 API Key（掩码显示）。点击输入框可修改；留空并保存则保留原密钥。
              </p>
            )}
            <p className="mt-1 text-xs text-zinc-500">
              在{' '}
              <a
                href="https://platform.deepseek.com/"
                target="_blank"
                rel="noreferrer"
                className="text-indigo-400 hover:underline"
              >
                DeepSeek 开放平台
              </a>{' '}
              获取，仅保存在本机 `backend/.local/settings.json`，不会进入 Git。
            </p>
          </Field>

          <Field label="Whisper 转写模型" required>
            <WhisperModelSelect
              options={options.whisper_options}
              value={whisperModel}
              onChange={setWhisperModel}
              platformLabel={options.platform_label}
            />
          </Field>

          <Field label="DeepSeek 总结模型">
            <ModelSelect
              options={options.deepseek_options}
              value={deepseekModel}
              onChange={setDeepseekModel}
            />
          </Field>

          {error && (
            <p className="rounded-lg bg-red-900/30 px-3 py-2 text-sm text-red-300">{error}</p>
          )}

          <button
            type="submit"
            disabled={saving}
            className="w-full rounded-xl bg-[var(--sv-accent)] py-3 text-sm font-medium text-[var(--sv-accent-fg)] hover:opacity-90 disabled:opacity-50"
          >
            {saving ? '保存中...' : isUpdate ? '保存' : '保存，下一步下载模型'}
          </button>
        </form>
      </div>
    </div>
  )
}

function Field({
  label,
  required,
  children,
}: {
  label: string
  required?: boolean
  children: React.ReactNode
}) {
  return (
    <div>
      <label className="mb-2 block text-sm font-medium text-[var(--sv-fg)]">
        {label}
        {required && <span className="text-red-400"> *</span>}
      </label>
      {children}
    </div>
  )
}

function ModelSelect({
  options,
  value,
  onChange,
}: {
  options: ModelOption[]
  value: string
  onChange: (v: string) => void
}) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} className={inputClass}>
      {options.map((o) => (
        <option key={o.id} value={o.id}>
          {o.label}
        </option>
      ))}
    </select>
  )
}

const inputClass =
  'w-full rounded-lg border border-[var(--sv-border)] bg-[var(--sv-bg)] px-3 py-2.5 text-sm text-[var(--sv-fg)] focus:border-[var(--sv-accent)] focus:outline-none'
