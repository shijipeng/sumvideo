import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { HistoryPanel } from './components/HistoryPanel'
import { ModelDownloadGate } from './components/ModelDownloadGate'
import { MindMapView } from './components/MindMapView'
import { NotesView } from './components/NotesView'
import { IllustratedNotesView } from './components/IllustratedNotesView'
import { SetupGate } from './components/SetupGate'
import { ImportUrlField } from './components/ImportUrlField'
import { UploadButton } from './components/UploadButton'
import { VideoPlayer, type VideoPlayerHandle } from './components/VideoPlayer'
import { useTaskPolling } from './hooks/useTaskPolling'
import {
  clearSettings,
  deleteHistory,
  exportMindmapMd,
  exportNotesMd,
  getHistory,
  getSettings,
  getStatus,
  retryVideo,
  uploadVideo,
  importVideoUrl,
  videoStreamUrl,
} from './lib/api'
import { pickVideoFile, readVideoAsFile } from './lib/runtime'
import { formatUnknownError } from './lib/errors'
import { canResumeFromNotes, formatTaskError } from './lib/taskResume'
import type { RetryFromStage } from './lib/api'
import { buildMindmapMarkdown, canBuildMindmap } from './lib/mindmapMarkdown'
import { sectionHasBody } from './lib/sectionRender'
import { useTheme } from './theme/ThemeContext'
import type { HistoryItem, NoteSection, VideoStatus } from './types'

type AppPhase = 'loading' | 'setup' | 'download' | 'main'

const SIDEBAR_KEY = 'sumvideo-sidebar-collapsed'

function findActiveSectionIndex(sections: NoteSection[], time: number) {
  for (let i = sections.length - 1; i >= 0; i--) {
    if (time >= sections[i].start_time) return i
  }
  return -1
}

function resolvePhase(s: {
  settings_ready?: boolean
  model_ready?: boolean
  ready?: boolean
  api_configured?: boolean
  whisper_model?: string | null
}): AppPhase {
  const settingsReady =
    s.settings_ready ?? Boolean(s.api_configured && s.whisper_model)
  if (!settingsReady) return 'setup'
  if (!s.model_ready) return 'download'
  return 'main'
}

function readSidebarCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_KEY) === '1'
  } catch {
    return false
  }
}

export default function App() {
  const [phase, setPhase] = useState<AppPhase>('loading')
  const [setupIsUpdate, setSetupIsUpdate] = useState(false)
  const [bootError, setBootError] = useState<string | null>(null)

  const refreshPhase = useCallback(async () => {
    setBootError(null)
    try {
      const s = await getSettings()
      setPhase(resolvePhase(s))
      return s
    } catch (e) {
      const msg = e instanceof Error ? e.message : '无法连接后端'
      setBootError(msg)
      setPhase('setup')
      return null
    }
  }, [])

  useEffect(() => {
    refreshPhase()
  }, [refreshPhase])

  if (phase === 'loading') {
    return (
      <div className="flex min-h-dvh flex-col items-center justify-center gap-3 bg-[var(--sv-bg)] px-4 text-[var(--sv-fg-muted)]">
        <p>加载中...</p>
        {bootError && <p className="max-w-md text-center text-sm text-[var(--sv-danger-fg)]">{bootError}</p>}
      </div>
    )
  }

  if (phase === 'setup') {
    return (
      <div className="flex min-h-dvh flex-col">
        {bootError && (
          <p className="shrink-0 bg-[var(--sv-danger-bg)] px-4 py-2 text-center text-sm text-[var(--sv-danger-fg)]">
            {bootError}
          </p>
        )}
        <SetupGate
          isUpdate={setupIsUpdate}
          onSaved={async () => {
            await refreshPhase()
          }}
        />
      </div>
    )
  }

  if (phase === 'download') {
    return (
      <ModelDownloadGate
        onComplete={() => setPhase('main')}
        onBackToSettings={() => {
          setSetupIsUpdate(true)
          setPhase('setup')
        }}
      />
    )
  }

  return (
    <MainWorkspace
      onOpenSettings={() => {
        setSetupIsUpdate(true)
        setPhase('setup')
      }}
      onResetSettings={async () => {
        if (!confirm('清除全部配置并返回初始设置页？')) return
        await clearSettings()
        setSetupIsUpdate(false)
        setPhase('setup')
      }}
    />
  )
}

function MainWorkspace({
  onOpenSettings,
  onResetSettings,
}: {
  onOpenSettings: () => void
  onResetSettings: () => void
}) {
  const { theme, toggleTheme } = useTheme()
  const playerRef = useRef<VideoPlayerHandle>(null)
  const [localVideoUrl, setLocalVideoUrl] = useState<string | null>(null)
  const [localFile, setLocalFile] = useState<File | null>(null)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [polling, setPolling] = useState(false)
  const [retryInFlight, setRetryInFlight] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [importing, setImporting] = useState(false)
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [loadedResult, setLoadedResult] = useState<VideoStatus | null>(null)
  const [activeSectionIndex, setActiveSectionIndex] = useState(-1)
  const [error, setError] = useState<string | null>(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(readSidebarCollapsed)
  const [rightTab, setRightTab] = useState<'notes' | 'illustrated' | 'mindmap'>('notes')
  const [duplicateModal, setDuplicateModal] = useState<{
    file?: File
    url?: string
    existingId: string
    filename: string
  } | null>(null)
  const [transcriptCorrection, setTranscriptCorrection] = useState(false)
  const [savingCorrectionPref, setSavingCorrectionPref] = useState(false)

  const { status: pollStatus } = useTaskPolling(taskId, polling)

  const displayStatus = pollStatus ?? loadedResult
  const sections: NoteSection[] = displayStatus?.chapters ?? []
  const overview = displayStatus?.summary ?? null
  const hasStructuredNotes = sections.some((s) => sectionHasBody(s))
  const mindmapReady = canBuildMindmap(overview, sections)
  const illustratedReady =
    displayStatus?.status === 'done' &&
    Boolean(displayStatus.transcript || displayStatus.transcript_segments?.length)

  const notesMetaLabel = useMemo(() => {
    const meta = displayStatus?.notes_meta
    const typeLabel = displayStatus?.video_type_label
    if (!meta && !typeLabel) return null
    const parts: string[] = []
    if (meta?.industry?.trim()) parts.push(meta.industry.trim())
    if (typeLabel) parts.push(typeLabel)
    const label = parts.length ? parts.join(' · ') : null
    const bg = meta?.background_summary?.trim()
    if (bg && label) return `${label} — ${bg.length > 60 ? `${bg.slice(0, 60)}…` : bg}`
    return bg || label
  }, [displayStatus?.notes_meta, displayStatus?.video_type_label])

  const frameStillPolling =
    displayStatus?.status === 'done' &&
    (displayStatus.frame_status === 'pending' ||
      displayStatus.frame_status === 'processing')
  const mindmapMarkdown = useMemo(
    () =>
      displayStatus
        ? buildMindmapMarkdown(displayStatus.filename, overview, sections)
        : '',
    [displayStatus, overview, sections],
  )

  const videoSrc = useMemo(() => {
    if (localVideoUrl) return localVideoUrl
    if (!taskId) return null
    const status = pollStatus?.status ?? loadedResult?.status
    if (status === 'done') return videoStreamUrl(taskId)
    return null
  }, [localVideoUrl, taskId, pollStatus?.status, loadedResult?.status])

  const refreshHistory = useCallback(async () => {
    try {
      const list = await getHistory()
      setHistory(list)
    } catch {
      /* ignore */
    }
  }, [])

  useEffect(() => {
    refreshHistory()
  }, [refreshHistory])

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_KEY, sidebarCollapsed ? '1' : '0')
    } catch {
      /* ignore */
    }
  }, [sidebarCollapsed])

  useEffect(() => {
    if (!pollStatus) return
    if (pollStatus.status === 'processing' || pollStatus.status === 'pending') {
      setRetryInFlight(false)
    }
    if (pollStatus.status === 'done') {
      setRetryInFlight(false)
      refreshHistory()
      setLoadedResult(pollStatus)
      if (pollStatus.status === 'done') {
        if (localVideoUrl?.startsWith('blob:')) {
          URL.revokeObjectURL(localVideoUrl)
          setLocalVideoUrl(null)
        }
      }
      const frameRunning =
        pollStatus.frame_status === 'pending' ||
        pollStatus.frame_status === 'processing'
      if (!frameRunning) {
        setPolling(false)
      }
    } else if (pollStatus.status === 'error') {
      setRetryInFlight(false)
      setPolling(false)
      refreshHistory()
      setError(`处理失败：${formatTaskError(pollStatus)}`)
      console.error('[SumVideo] 处理失败', pollStatus)
      setLoadedResult(pollStatus)
    }
  }, [pollStatus, refreshHistory, localVideoUrl, taskId])

  const startProcessing = async (
    res: Awaited<ReturnType<typeof uploadVideo>>,
    opts?: { file?: File; url?: string },
  ) => {
    if (res.duplicate && res.existing) {
      setDuplicateModal({
        file: opts?.file,
        url: opts?.url,
        existingId: res.existing.id,
        filename: res.existing.filename,
      })
      return
    }
    if (res.task_id) {
      setTaskId(res.task_id)
      setPolling(true)
    } else {
      setError('未返回任务 ID，请查看后端日志')
    }
  }

  const handleFileSelect = async (file: File, force = false) => {
    setError(null)
    if (localVideoUrl?.startsWith('blob:')) URL.revokeObjectURL(localVideoUrl)
    setLocalVideoUrl(URL.createObjectURL(file))
    setLocalFile(file)
    setLoadedResult(null)
    setUploading(true)

    try {
      const res = await uploadVideo(file, force)
      await startProcessing(res, { file })
    } catch (e) {
      const msg = formatUnknownError(e, '上传失败')
      setError(msg)
      console.error('[SumVideo] 上传失败', e)
    } finally {
      setUploading(false)
    }
  }

  const handleVideoSelect = async (file?: File, force = false) => {
    if (file) {
      await handleFileSelect(file, force)
      return
    }
    const picked = await pickVideoFile()
    if (!picked) return
    try {
      const videoFile = await readVideoAsFile(picked.path, picked.name)
      await handleFileSelect(videoFile, force)
    } catch (e) {
      setError(formatUnknownError(e, '读取视频失败'))
      console.error('[SumVideo] 读取视频失败', e)
    }
  }

  const handleUrlImport = async (url: string, force = false) => {
    setError(null)
    if (localVideoUrl?.startsWith('blob:')) URL.revokeObjectURL(localVideoUrl)
    setLocalVideoUrl(null)
    setLocalFile(null)
    setLoadedResult(null)
    setImporting(true)

    try {
      const res = await importVideoUrl(url, force)
      await startProcessing(res, { url })
    } catch (e) {
      const msg = formatUnknownError(e, '导入失败')
      setError(msg)
      console.error('[SumVideo] URL 导入失败', e)
    } finally {
      setImporting(false)
    }
  }

  const loadHistoryItem = async (id: string) => {
    setError(null)
    if (localVideoUrl?.startsWith('blob:')) URL.revokeObjectURL(localVideoUrl)
    setLocalVideoUrl(null)
    setLocalFile(null)
    setTaskId(id)
    try {
      const data = await getStatus(id)
      setLoadedResult(data)
      const frameRunning =
        data.status === 'done' &&
        (data.frame_status === 'pending' || data.frame_status === 'processing')
      if (data.status === 'processing' || data.status === 'pending' || frameRunning) {
        setPolling(true)
      } else {
        setPolling(false)
      }
    } catch (e) {
      setPolling(false)
      setError(e instanceof Error ? e.message : '加载失败')
    }
  }

  const handleRetry = async (fromStage: RetryFromStage = 'auto') => {
    if (!taskId) return
    if (
      retryInFlight ||
      pollStatus?.status === 'processing' ||
      pollStatus?.status === 'pending' ||
      loadedResult?.status === 'processing'
    ) {
      return
    }
    setError(null)
    setRetryInFlight(true)
    try {
      const res = await retryVideo(taskId, fromStage)
      if (fromStage === 'frames_only') {
        setPolling(true)
      } else {
        setPolling(true)
        setLoadedResult(null)
      }
      if (res.resume_mode === 'notes_only') {
        setError(null)
      }
    } catch (e) {
      setRetryInFlight(false)
      setError(e instanceof Error ? e.message : '重新处理失败')
    }
  }

  const handleRetryFrames = () => handleRetry('frames_only')

  const showResumeNotes =
    displayStatus?.status === 'error' &&
    taskId &&
    canResumeFromNotes(displayStatus)

  const handleTimeUpdate = useCallback(
    (time: number) => {
      if (!sections.length) return
      setActiveSectionIndex(findActiveSectionIndex(sections, time))
    },
    [sections],
  )

  const handleSectionSelect = (sec: NoteSection) => {
    playerRef.current?.seekTo(sec.start_time)
  }

  const handleMindmapSeek = useCallback(
    (time: number, sectionIndex?: number) => {
      playerRef.current?.seekTo(time)
      if (sectionIndex != null && sectionIndex >= 0) {
        setActiveSectionIndex(sectionIndex)
      } else if (sections.length) {
        setActiveSectionIndex(findActiveSectionIndex(sections, time))
      }
    },
    [sections],
  )

  const progress = pollStatus?.progress ?? loadedResult?.progress ?? 0
  const progressMessage = pollStatus?.progress_message ?? ''
  const isProcessing =
    retryInFlight ||
    pollStatus?.status === 'processing' ||
    pollStatus?.status === 'pending' ||
    loadedResult?.status === 'processing' ||
    loadedResult?.status === 'pending'

  return (
    <div className="sv-app-shell bg-[var(--sv-bg)]">
      <header className="flex shrink-0 items-center justify-between border-b border-[var(--sv-border)] bg-[var(--sv-canvas)] px-4 py-3">
        <div className="flex items-center gap-3">
          <button
            type="button"
            title={sidebarCollapsed ? '展开历史' : '收起历史'}
            onClick={() => setSidebarCollapsed((c) => !c)}
            className="rounded-lg border border-[var(--sv-border)] px-2 py-1 text-sm text-[var(--sv-fg-muted)] hover:bg-[var(--sv-canvas-subtle)]"
          >
            {sidebarCollapsed ? '»' : '«'}
          </button>
          <div>
            <h1 className="text-lg font-semibold text-[var(--sv-fg)]">SumVideo</h1>
            <p className="text-xs text-[var(--sv-fg-muted)]">本地 AI 视频笔记</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <UploadButton
            onSelect={(f) => handleVideoSelect(f)}
            disabled={uploading || importing || isProcessing}
            uploading={uploading}
          />
          <ImportUrlField
            onImport={handleUrlImport}
            disabled={uploading || importing || isProcessing}
            importing={importing}
          />
          <button
            type="button"
            onClick={toggleTheme}
            className="rounded-lg border border-[var(--sv-border)] px-3 py-1.5 text-sm text-[var(--sv-fg)] hover:bg-[var(--sv-canvas-subtle)]"
            title={theme === 'dark' ? '切换浅色' : '切换深色'}
          >
            {theme === 'dark' ? '浅色' : '深色'}
          </button>
          <button
            type="button"
            onClick={onOpenSettings}
            className="rounded-lg border border-[var(--sv-border)] px-3 py-1.5 text-sm text-[var(--sv-fg)] hover:bg-[var(--sv-canvas-subtle)]"
          >
            设置
          </button>
          <button
            type="button"
            onClick={onResetSettings}
            className="rounded-lg px-3 py-1.5 text-sm text-[var(--sv-fg-muted)] hover:bg-[var(--sv-canvas-subtle)]"
          >
            重置
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 overflow-hidden">
        {!sidebarCollapsed && (
          <aside className="flex min-h-0 w-56 shrink-0 flex-col overflow-hidden border-r border-[var(--sv-border)] bg-[var(--sv-canvas)] p-3">
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-[var(--sv-fg-muted)]">
              历史记录
            </h2>
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
              <HistoryPanel
                items={history}
                selectedId={taskId}
                onSelect={loadHistoryItem}
                onDelete={async (id) => {
                  await deleteHistory(id)
                  if (taskId === id) {
                    setTaskId(null)
                    setLoadedResult(null)
                    if (localVideoUrl) {
                      URL.revokeObjectURL(localVideoUrl)
                      setLocalVideoUrl(null)
                    }
                  }
                  refreshHistory()
                }}
              />
            </div>
          </aside>
        )}

        <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          {error && (
            <div className="mx-4 mt-3 flex shrink-0 flex-wrap items-center gap-3 rounded-lg bg-[var(--sv-danger-bg)] px-4 py-2 text-sm text-[var(--sv-danger-fg)]">
              <span className="flex-1">{error}</span>
              {displayStatus?.status === 'error' && taskId && (
                <>
                  {showResumeNotes && (
                    <button
                      type="button"
                      className="rounded-lg bg-[var(--sv-accent)] px-3 py-1 text-xs text-[var(--sv-accent-fg)] hover:opacity-90"
                      onClick={() => handleRetry('notes_only')}
                    >
                      从笔记阶段继续
                    </button>
                  )}
                  <button
                    type="button"
                    className="rounded-lg border border-[var(--sv-danger-fg)]/30 px-3 py-1 text-xs hover:opacity-80"
                    onClick={() => handleRetry(showResumeNotes ? 'full' : 'auto')}
                  >
                    {showResumeNotes ? '从头重新处理' : '重新处理'}
                  </button>
                </>
              )}
            </div>
          )}

          {isProcessing && !frameStillPolling && (
            <div className="mx-4 mt-3 shrink-0">
              <div className="mb-1 flex justify-between text-xs text-[var(--sv-fg-muted)]">
                <span>{progressMessage || '处理中…'}</span>
                <span>{Math.round(progress)}%</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-[var(--sv-canvas-subtle)]">
                <div
                  className="h-full bg-[var(--sv-accent)] transition-all duration-300"
                  style={{ width: `${Math.max(progress, 2)}%` }}
                />
              </div>
            </div>
          )}

          <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden p-4">
            <div className="shrink-0 space-y-2 overflow-hidden">
              <VideoPlayer
                ref={playerRef}
                src={videoSrc}
                onTimeUpdate={handleTimeUpdate}
              />
              {displayStatus?.status === 'done' && !isProcessing && (
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="rounded-lg border border-[var(--sv-border)] px-3 py-1.5 text-sm text-[var(--sv-fg)] hover:bg-[var(--sv-canvas-subtle)]"
                    onClick={() =>
                      exportNotesMd(
                        displayStatus.filename,
                        overview || '',
                        sections,
                      )
                    }
                  >
                    导出笔记
                  </button>
                  {mindmapReady && (
                    <button
                      type="button"
                      className="rounded-lg border border-[var(--sv-border)] px-3 py-1.5 text-sm text-[var(--sv-fg)] hover:bg-[var(--sv-canvas-subtle)]"
                      onClick={() =>
                        exportMindmapMd(displayStatus.filename, mindmapMarkdown)
                      }
                    >
                      导出思维导图
                    </button>
                  )}
                  <button
                    type="button"
                    className="rounded-lg border border-[var(--sv-border)] px-3 py-1.5 text-sm text-[var(--sv-fg)] hover:bg-[var(--sv-canvas-subtle)] disabled:cursor-not-allowed disabled:opacity-50"
                    onClick={() => handleRetry('notes_only')}
                    disabled={isProcessing}
                  >
                    重新生成 AI 笔记
                  </button>
                  <button
                    type="button"
                    className="rounded-lg border border-[var(--sv-border)] px-3 py-1.5 text-sm text-[var(--sv-fg)] hover:bg-[var(--sv-canvas-subtle)] disabled:cursor-not-allowed disabled:opacity-50"
                    onClick={handleRetryFrames}
                    disabled={frameStillPolling || isProcessing}
                  >
                    重新生成配图
                  </button>
                  <button
                    type="button"
                    className="rounded-lg border border-[var(--sv-border)] px-3 py-1.5 text-sm text-[var(--sv-fg)] hover:bg-[var(--sv-canvas-subtle)] disabled:cursor-not-allowed disabled:opacity-50"
                    onClick={() => {
                      if (taskId) handleRetry('full')
                      else if (localFile) handleVideoSelect(localFile, true)
                    }}
                    disabled={isProcessing}
                  >
                    强制从头处理
                  </button>
                </div>
              )}
            </div>

            <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-[var(--sv-border)] bg-[var(--sv-canvas)]">
              <div className="flex shrink-0 items-center gap-2 border-b border-[var(--sv-border)] px-3 py-2">
                <button
                  type="button"
                  onClick={() => setRightTab('notes')}
                  className={`rounded-md px-3 py-1 text-sm font-medium transition ${
                    rightTab === 'notes'
                      ? 'bg-[var(--sv-accent)] text-[var(--sv-accent-fg)]'
                      : 'text-[var(--sv-fg-muted)] hover:bg-[var(--sv-canvas-subtle)]'
                  }`}
                >
                  文字笔记
                </button>
                <button
                  type="button"
                  onClick={() => setRightTab('illustrated')}
                  disabled={!illustratedReady}
                  className={`rounded-md px-3 py-1 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${
                    rightTab === 'illustrated'
                      ? 'bg-[var(--sv-accent)] text-[var(--sv-accent-fg)]'
                      : 'text-[var(--sv-fg-muted)] hover:bg-[var(--sv-canvas-subtle)]'
                  }`}
                >
                  图文笔记
                </button>
                <button
                  type="button"
                  onClick={() => setRightTab('mindmap')}
                  disabled={!mindmapReady && displayStatus?.status !== 'done'}
                  className={`rounded-md px-3 py-1 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${
                    rightTab === 'mindmap'
                      ? 'bg-[var(--sv-accent)] text-[var(--sv-accent-fg)]'
                      : 'text-[var(--sv-fg-muted)] hover:bg-[var(--sv-canvas-subtle)]'
                  }`}
                >
                  思维导图
                </button>
              </div>
              {rightTab === 'notes' ? (
                <div data-notes-panel className="sv-notes-scroll p-4">
                  <NotesView
                    overview={hasStructuredNotes ? overview : null}
                    sections={sections}
                    activeIndex={activeSectionIndex}
                    onSectionSelect={handleSectionSelect}
                    transcript={displayStatus?.transcript}
                    transcriptSegments={displayStatus?.transcript_segments}
                    onTranscriptSeek={(t) => playerRef.current?.seekTo(t)}
                    legacySummary={!hasStructuredNotes ? overview : null}
                    metaLabel={notesMetaLabel}
                  />
                </div>
              ) : rightTab === 'illustrated' ? (
                <div data-notes-panel className="sv-notes-scroll p-4">
                  <IllustratedNotesView
                    sections={sections}
                    activeIndex={activeSectionIndex}
                    onSectionSelect={handleSectionSelect}
                    transcript={displayStatus?.transcript}
                    transcriptSegments={displayStatus?.transcript_segments}
                    onTranscriptSeek={(t) => playerRef.current?.seekTo(t)}
                    frameStatus={displayStatus?.frame_status}
                    frameProgressDone={displayStatus?.frame_progress_done}
                    frameProgressTotal={displayStatus?.frame_progress_total}
                    frameErrorMessage={displayStatus?.frame_error_message}
                    onRetryFrames={taskId ? handleRetryFrames : undefined}
                  />
                </div>
              ) : (
                <div className="flex min-h-0 flex-1 flex-col overflow-hidden p-4">
                  <MindMapView
                    filename={displayStatus?.filename ?? '视频'}
                    overview={overview}
                    sections={sections}
                    onSeek={handleMindmapSeek}
                  />
                </div>
              )}
            </section>
          </div>
        </main>
      </div>

      {duplicateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--sv-overlay)] p-4">
          <div className="max-w-md rounded-xl border border-[var(--sv-border)] bg-[var(--sv-canvas)] p-6 shadow-xl">
            <h3 className="text-lg font-medium text-[var(--sv-fg)]">检测到重复视频</h3>
            <p className="mt-2 text-sm text-[var(--sv-fg-muted)]">
              「{duplicateModal.filename}」已处理过，是否使用已有结果？
            </p>
            <div className="mt-6 flex gap-3">
              <button
                type="button"
                className="flex-1 rounded-lg bg-[var(--sv-accent)] px-4 py-2 text-sm text-[var(--sv-accent-fg)] hover:opacity-90"
                onClick={() => {
                  setDuplicateModal(null)
                  loadHistoryItem(duplicateModal.existingId)
                }}
              >
                使用已有结果
              </button>
              <button
                type="button"
                className="flex-1 rounded-lg border border-[var(--sv-border)] px-4 py-2 text-sm text-[var(--sv-fg)] hover:bg-[var(--sv-canvas-subtle)]"
                onClick={async () => {
                  const { existingId, file, url } = duplicateModal
                  setDuplicateModal(null)
                  if (localVideoUrl?.startsWith('blob:')) {
                    URL.revokeObjectURL(localVideoUrl)
                    setLocalVideoUrl(null)
                  }
                  if (url) {
                    setTaskId(existingId)
                    setLoadedResult(null)
                    setPolling(true)
                    setError(null)
                    try {
                      await retryVideo(existingId, 'full')
                      await refreshHistory()
                    } catch (e) {
                      setPolling(false)
                      setError(e instanceof Error ? e.message : '重新处理失败')
                    }
                    return
                  }
                  if (file) {
                    setLocalFile(file)
                    setLocalVideoUrl(URL.createObjectURL(file))
                  }
                  setTaskId(existingId)
                  setLoadedResult(null)
                  setPolling(true)
                  setError(null)
                  try {
                    await retryVideo(existingId, 'full')
                    await refreshHistory()
                  } catch (e) {
                    setPolling(false)
                    setError(e instanceof Error ? e.message : '重新处理失败')
                  }
                }}
              >
                重新处理
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
