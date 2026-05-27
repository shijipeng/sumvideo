import { stripNoteLabel } from './noteText'
import type { NoteSection } from '../types'

const SEEK_ATTR_RE = /data-sv-seek="([\d.]+)"/
const SECTION_ATTR_RE = /data-sv-section="(\d+)"/

/** 避免 markmap / markdown 特殊字符破坏结构 */
function escapeMd(text: string): string {
  return text.replace(/[\r\n]+/g, ' ').replace(/#/g, '').trim()
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/** 节点 HTML 内嵌跳转时间，点击导图时解析 */
function seekSpan(
  time: number,
  text: string,
  sectionIndex?: number,
): string {
  const sec =
    sectionIndex != null ? ` data-sv-section="${sectionIndex}"` : ''
  return `<span data-sv-seek="${time}"${sec}>${escapeHtml(text)}</span>`
}

export function parseSeekFromNodeContent(content: string): {
  time: number
  sectionIndex?: number
} | null {
  const seekM = content.match(SEEK_ATTR_RE)
  if (!seekM) return null
  const sectionM = content.match(SECTION_ATTR_RE)
  return {
    time: Number(seekM[1]),
    sectionIndex: sectionM ? Number(sectionM[1]) : undefined,
  }
}

/** 按 markmap 的 data-path 前缀向上查找最近可跳转节点 */
export function resolveSeekByPath(
  path: string,
  index: Map<string, { time: number; sectionIndex?: number }>,
): { time: number; sectionIndex?: number } | null {
  const parts = path.split('.')
  for (let len = parts.length; len > 0; len--) {
    const hit = index.get(parts.slice(0, len).join('.'))
    if (hit) return hit
  }
  return null
}

function basename(filename: string): string {
  const i = filename.lastIndexOf('.')
  return i > 0 ? filename.slice(0, i) : filename
}

/**
 * 由现有笔记生成 markmap 可用的 Markdown 大纲（不额外调用 API）
 */
export function buildMindmapMarkdown(
  filename: string,
  overview: string | null | undefined,
  sections: NoteSection[],
): string {
  const lines: string[] = [
    `# ${seekSpan(0, escapeMd(basename(filename)) || '视频笔记')}`,
  ]

  const ov = overview?.trim()
  if (ov) {
    lines.push(
      '',
      `## ${seekSpan(0, '概述')}`,
      '',
      seekSpan(0, escapeMd(stripNoteLabel(ov))),
    )
  }

  sections.forEach((sec, i) => {
    const title = escapeMd(sec.title) || '未命名分段'
    const t = sec.start_time
    lines.push('', `## ${seekSpan(t, title, i)}`)
    const lead = sec.lead ? stripNoteLabel(sec.lead) : ''
    if (lead) {
      lines.push('', seekSpan(t, escapeMd(lead), i))
    }
    const points = (sec.points ?? []).map((p) => stripNoteLabel(p)).filter(Boolean)
    if (points.length) {
      lines.push('', `### ${seekSpan(t, '要点', i)}`)
      for (const p of points) {
        lines.push(`- ${seekSpan(t, escapeMd(p), i)}`)
      }
    }
  })

  if (lines.length <= 1 && !sections.length) {
    lines.push('', '（暂无笔记内容，处理完成后再查看思维导图）')
  }

  return lines.join('\n')
}

export function canBuildMindmap(
  overview: string | null | undefined,
  sections: NoteSection[],
): boolean {
  if (overview?.trim()) return true
  return sections.some((s) => s.title || s.lead || (s.points && s.points.length > 0))
}
