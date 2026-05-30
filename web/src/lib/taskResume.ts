import type { VideoStatus } from '../types'

/** 失败任务是否可从笔记阶段继续（与后端 resume_available 一致，前端兜底判断） */
export function canResumeFromNotes(status: VideoStatus | null | undefined): boolean {
  if (!status || status.status !== 'error') return false
  if (status.resume_available) return true
  const segs = status.transcript_segments
  const text = (status.transcript || '').trim()
  if (!segs?.length || text.length < 50) return false
  if (status.error_message) return true
  const markers = ['处理已中断', '处理超时', '请重新上传', 'DeepSeek API', '笔记生成超过']
  return !markers.some((m) => text.startsWith(m) || text.includes(m))
}

export function formatTaskError(status: VideoStatus | null | undefined): string {
  const msg =
    status?.error_message?.trim() ||
    (status?.status === 'error' && !canResumeFromNotes(status)
      ? status.transcript?.trim()
      : '') ||
    '视频处理失败'
  return msg.length > 300 ? `${msg.slice(0, 300)}…` : msg
}
