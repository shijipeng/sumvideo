import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Markmap } from 'markmap-view'
import { Transformer } from 'markmap-lib'
import type { INode } from 'markmap-common'
import {
  buildMindmapMarkdown,
  canBuildMindmap,
  parseSeekFromNodeContent,
  resolveSeekByPath,
} from '../lib/mindmapMarkdown'
import type { NoteSection } from '../types'

const transformer = new Transformer()

type SeekHit = { time: number; sectionIndex?: number }

function buildSeekIndex(root: INode | undefined, map: Map<string, SeekHit>) {
  map.clear()
  if (!root) return

  function walk(node: INode) {
    const parsed = parseSeekFromNodeContent(node.content)
    if (parsed) map.set(node.state.path, parsed)
    node.children.forEach(walk)
  }

  walk(root)
}

interface Props {
  filename: string
  overview?: string | null
  sections: NoteSection[]
  onSeek?: (time: number, sectionIndex?: number) => void
}

export function MindMapView({ filename, overview, sections, onSeek }: Props) {
  const svgRef = useRef<SVGSVGElement>(null)
  const markmapRef = useRef<Markmap | null>(null)
  const seekIndexRef = useRef<Map<string, SeekHit>>(new Map())
  const [error, setError] = useState<string | null>(null)

  const markdown = useMemo(
    () => buildMindmapMarkdown(filename, overview, sections),
    [filename, overview, sections],
  )

  const hasContent = canBuildMindmap(overview, sections)

  const handleNodeClick = useCallback(
    (e: MouseEvent) => {
      if (!onSeek) return
      const target = e.target as Element
      if (target.closest('circle')) return

      const g = target.closest('g.markmap-node')
      if (!g) return
      const path = g.getAttribute('data-path')
      if (!path) return

      const hit = resolveSeekByPath(path, seekIndexRef.current)
      if (hit == null) return

      e.preventDefault()
      e.stopPropagation()
      onSeek(hit.time, hit.sectionIndex)
    },
    [onSeek],
  )

  useEffect(() => {
    if (!svgRef.current || !hasContent) return

    let cancelled = false

    async function render() {
      try {
        setError(null)
        const { root } = transformer.transform(markdown)
        if (cancelled || !svgRef.current) return

        if (!markmapRef.current) {
          markmapRef.current = Markmap.create(svgRef.current, {
            zoom: true,
            pan: true,
            autoFit: true,
            embedGlobalCSS: true,
            paddingX: 16,
          })
        }
        await markmapRef.current.setData(root)
        buildSeekIndex(markmapRef.current.state.data, seekIndexRef.current)
        markmapRef.current.fit()
      } catch (e) {
        setError(e instanceof Error ? e.message : '思维导图渲染失败')
      }
    }

    render()

    return () => {
      cancelled = true
    }
  }, [markdown, hasContent])

  useEffect(() => {
    const svg = svgRef.current
    if (!svg || !onSeek || !hasContent) return
    svg.addEventListener('click', handleNodeClick)
    return () => svg.removeEventListener('click', handleNodeClick)
  }, [handleNodeClick, onSeek, hasContent])

  useEffect(() => {
    return () => {
      markmapRef.current?.destroy()
      markmapRef.current = null
      seekIndexRef.current.clear()
    }
  }, [])

  if (!hasContent) {
    return (
      <p className="text-sm text-[var(--sv-fg-muted)]">
        处理完成后将根据 AI 笔记自动生成思维导图
      </p>
    )
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col sv-mindmap">
      <p className="mb-2 shrink-0 text-xs text-[var(--sv-fg-muted)]">
        点击节点跳转视频 · 滚轮缩放 · 拖拽平移 · 圆点折叠子节点
      </p>
      {error && (
        <p className="mb-2 shrink-0 text-sm text-[var(--sv-danger-fg)]">{error}</p>
      )}
      <div className="min-h-0 flex-1 overflow-hidden rounded-md border border-[var(--sv-border)] bg-[var(--sv-bg)]">
        <svg ref={svgRef} className="h-full w-full" />
      </div>
    </div>
  )
}
