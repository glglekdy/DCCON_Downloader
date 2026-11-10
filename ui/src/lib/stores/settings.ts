import { getCurrentWindow } from '@tauri-apps/api/window'
import { get, writable } from 'svelte/store'
import { getSettings, saveSettings, type Settings } from '../api'

export const settings = writable<Settings | null>(null)

/** 테마와 모션 설정을 문서와 창에 반영한다. */
async function apply(s: Settings): Promise<void> {
  const root = document.documentElement
  if (s.theme === 'system') delete root.dataset.theme
  else root.dataset.theme = s.theme
  if (s.reduce_motion) root.dataset.reduceMotion = ''
  else delete root.dataset.reduceMotion
  try {
    await getCurrentWindow().setTheme(s.theme === 'system' ? null : s.theme)
  } catch {
    // 창 API 가 없는 환경(브라우저 미리보기, 테스트)에서는 CSS 만 바뀐다.
  }
}

export async function loadSettings(): Promise<Settings> {
  const s = await getSettings()
  settings.set(s)
  await apply(s)
  return s
}

export async function updateSettings(patch: Partial<Settings>): Promise<Settings> {
  const current = get(settings) ?? (await getSettings())
  const next = { ...current, ...patch }
  await saveSettings(next)
  settings.set(next)
  await apply(next)
  return next
}
