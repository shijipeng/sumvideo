/** 解析 FastAPI / fetch 错误为可读文案 */
export function parseApiError(body: unknown, fallback: string): string {
  if (!body || typeof body !== 'object') return fallback
  const detail = (body as { detail?: unknown }).detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === 'object' && item && 'msg' in item) {
          return String((item as { msg: unknown }).msg)
        }
        return JSON.stringify(item)
      })
      .join('；')
  }
  return fallback
}

export function formatUnknownError(e: unknown, fallback: string): string {
  if (e instanceof TypeError && e.message === 'Failed to fetch') {
    return '无法连接后端，请确认已运行 ./scripts/start-backend.sh（http://127.0.0.1:8000）'
  }
  if (e instanceof Error) return e.message || fallback
  return fallback
}
