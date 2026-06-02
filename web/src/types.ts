export interface TranscriptSegment {
  start_time: number
  end_time: number
  text: string
}

export interface SectionFrame {
  time: number
  url: string
}

export interface NoteSection {
  title: string
  start_time: number
  end_time: number
  format?: 'prose' | 'bullets' | 'steps' | 'qa'
  lead?: string
  content?: string
  points?: string[]
  steps?: string[]
  qa?: { q: string; a: string }[]
  /** 节内多图（按时间排序） */
  frames?: SectionFrame[]
  /** 首张配图，兼容旧数据 */
  thumbnail?: string | null
}

/** @deprecated 使用 NoteSection */
export type Chapter = NoteSection

export interface NotesMeta {
  schema_version?: number
  video_type: string
  summary_style?: string
  industry?: string
  confidence?: number
  type_reason?: string
  video_type_raw?: string
  background_summary?: string
  structure_style?: string
}

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
  notes_meta?: NotesMeta | null
  frame_status?: 'pending' | 'processing' | 'done' | 'error' | 'skipped'
  frame_progress_done?: number
  frame_progress_total?: number
  frame_error_message?: string | null
  video_type_label?: string | null
  /** 失败原因（与 transcript 分离，便于断点续跑） */
  error_message?: string | null
  /** 可从笔记阶段继续（转写已保存） */
  resume_available?: boolean
  created_at: string
  updated_at?: string
  /** 桌面端：用户原视频绝对路径 */
  source_path?: string | null
}

export interface HistoryItem {
  id: string
  filename: string
  status: string
  progress: number
  created_at: string
  updated_at?: string
  source_path?: string | null
}

export interface UploadResponse {
  task_id?: string
  source_path?: string
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
  bytes_downloaded?: number
  bytes_total?: number
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
