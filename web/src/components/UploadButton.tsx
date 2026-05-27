import { useRef } from 'react'

interface Props {
  onFileSelect: (file: File) => void
  disabled?: boolean
  uploading?: boolean
}

const ACCEPT = '.mp4,.m4v,.avi,.mov,.mkv,.webm,.flv,.wmv,.mpeg,.mpg,.3gp,.ts'

export function UploadButton({ onFileSelect, disabled, uploading }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        className="hidden"
        disabled={disabled}
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) onFileSelect(file)
          e.target.value = ''
        }}
      />
      <button
        type="button"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        className="rounded-lg bg-[var(--sv-accent)] px-3 py-1.5 text-sm font-medium text-[var(--sv-accent-fg)] hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {uploading ? '上传中…' : '上传视频'}
      </button>
    </>
  )
}
