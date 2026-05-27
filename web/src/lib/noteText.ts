/** 去掉模型或旧版 UI 可能带上的「总：」「分：」等前缀 */
export function stripNoteLabel(text: string): string {
  let s = text.trim()
  const prefixes = [
    /^总[：:]\s*/,
    /^分[：:]\s*/,
    /^总述[：:]\s*/,
    /^分述[：:]\s*/,
  ]
  for (const re of prefixes) {
    s = s.replace(re, '')
  }
  return s.trim()
}
