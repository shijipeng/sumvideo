export interface TranscriptSegment {
  start_time: number
  end_time: number
  text: string
}

export interface NoteSection {
  title: string
  start_time: number
  end_time: number
  lead?: string
  points?: string[]
}

/** @deprecated 使用 NoteSection */
export type Chapter = NoteSection

export interface VideoStatus {
  id: string
  filename: string
  status: 'pending' | 'processing' | 'done' | 'error'
  progress: number
  progress_message?: string
  transcript?: string | null
  transcript_segments?: TranscriptSegment[] | null
  chapters?: NoteSection[] | null
  /** 概述（方案 B）；旧数据可能为整篇 Markdown */
  summary?: string | null
  created_at: string
  updated_at?: string
}

export interface HistoryItem {
  id: string
  filename: string
  status: string
  progress: number
  created_at: string
  updated_at?: string
}

export interface UploadResponse {
  task_id?: string
  duplicate: boolean
  existing?: {
    id: string
    filename: string
    created_at: string
  }
  message?: string
}

export interface ModelOption {
  id: string
  label: string
}

export interface WhisperModelOption {
  id: string
  label: string
  engine: string
  group: string
  platform_hint: string
  supported_on_current_platform: boolean
  recommended: boolean
}

export interface ModelDownloadHint {
  model_id: string
  label: string
  engine: string
  size_gb: number
  eta_text: string
  cache_dir: string
  mirror_hint: string
}

export interface ModelDownloadState {
  status: string
  progress: number
  message: string
  model_id: string | null
  error: string | null
  model_ready?: boolean
  ready?: boolean
}

export interface AppSettings {
  ready: boolean
  settings_ready: boolean
  model_ready: boolean
  api_configured: boolean
  /** 已保存 Key 的掩码，用于密码框展示（非明文） */
  api_key_masked?: string
  /** 本地曾保存过无效 Key（如误填网址） */
  api_key_invalid?: boolean
  whisper_model: string | null
  deepseek_model: string
  platform: string
  platform_label: string
  recommended_whisper_model: string
  whisper_options: WhisperModelOption[]
  deepseek_options: ModelOption[]
  model_download_hint?: ModelDownloadHint | null
}
