interface Props {
  onFileSelect: (file: File) => void
  disabled?: boolean
  uploading?: boolean
}

const ACCEPT = '.mp4,.m4v,.avi,.mov,.mkv,.webm,.flv,.wmv,.mpeg,.mpg,.3gp,.ts'

export function Uploader({ onFileSelect, disabled, uploading }: Props) {
  return (
    <label
      className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-4 py-6 transition ${
        disabled
          ? 'cursor-not-allowed border-zinc-800 text-zinc-600'
          : 'border-indigo-500/40 text-zinc-400 hover:border-indigo-500 hover:bg-indigo-500/5'
      }`}
    >
      <input
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
      <span className="text-2xl">+</span>
      <span className="mt-1 text-sm font-medium">
        {uploading ? '上传中...' : '选择本地视频'}
      </span>
      <span className="mt-1 text-xs text-zinc-600">MP4 / MOV / MKV 等</span>
    </label>
  )
}
