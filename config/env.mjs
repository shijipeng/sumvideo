import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))

let _cache

export function loadEnvironments() {
  if (!_cache) {
    _cache = JSON.parse(
      readFileSync(join(__dirname, 'environments.json'), 'utf8'),
    )
  }
  return _cache
}

/** @returns {'dev' | 'desktop'} */
export function resolveProfileName({ isPackaged, isElectronDev }) {
  if (isPackaged) return 'desktop'
  if (isElectronDev) return 'dev'
  return 'dev'
}

export function getProfile(name) {
  const envs = loadEnvironments()
  const profile = envs[name]
  if (!profile) throw new Error(`未知环境配置: ${name}`)
  return profile
}

export function getElectronProfile({ isPackaged, isElectronDev }) {
  return getProfile(resolveProfileName({ isPackaged, isElectronDev }))
}
