// Rust 커맨드 래퍼. 자료형은 src-tauri/src/dto.rs, crates/core 의 serde 출력(snake_case)과 같다.
// Tauri 는 커맨드 인자를 camelCase 키로 받는다 (search_type -> searchType).
import { invoke } from '@tauri-apps/api/core'
import { listen, type UnlistenFn } from '@tauri-apps/api/event'

export type Site = 'dccon' | 'arca'
export type TopKind = 'day' | 'week' | 'month' | 'official'
export type ThemeMode = 'system' | 'light' | 'dark'

export interface Settings {
  download_dir: string
  concurrency: number
  save_main_image: boolean
  write_meta_json: boolean
  reduce_motion: boolean
  theme: ThemeMode
  animate_gifs: boolean
  check_updates: boolean
  skipped_version: string
  recent_packages: number[]
}

/** 검색 결과·인기 목록의 한 줄 (상세 전). */
export interface Brief {
  idx: number
  title: string
  seller: string
  thumb_url: string
}

export interface Item {
  idx: number
  title: string
  sort: number
  ext: string
  path: string
  thumb: string
}

export interface Package {
  idx: number
  title: string
  description: string
  seller: string
  price: string
  reg_date: string
  main_img_path: string
  list_img_path: string
  items: Item[]
  tags: string[]
}

export interface ListPage {
  items: Brief[]
  page: number
  pages: number
  total: number | null
}

export type Query = { kind: 'search'; word: string } | { kind: 'ids'; ids: number[] }

export interface Job {
  id: number
  title: string
  sorts?: number[] | null
}

export interface ReleaseInfo {
  version: string
  notes: string
  page_url: string
  can_apply: boolean
}

export interface CacheStats {
  files: number
  bytes: number
}

/** 커맨드가 실패하면 이 모양으로 던져진다. */
export interface CmdError {
  kind: string
  message: string
}

export function isCmdError(e: unknown): e is CmdError {
  return typeof e === 'object' && e !== null && 'kind' in e && 'message' in e
}

// --- 커맨드 -------------------------------------------------------------

export const getSettings = () => invoke<Settings>('get_settings')
export const saveSettings = (settings: Settings) => invoke<void>('save_settings', { settings })
export const beginView = () => invoke<number>('begin_view')
export const listTop = (kind: TopKind) => invoke<ListPage>('list_top', { kind })
export const listAll = (page: number) => invoke<ListPage>('list_all', { page })
export const listArca = (kind: string, page: number) =>
  invoke<ListPage>('list_arca', { kind, page })
export const search = (site: Site, word: string, searchType: string, page: number) =>
  invoke<ListPage>('search', { site, word, searchType, page })
export const openPackage = (site: Site, id: number) =>
  invoke<Package>('open_package', { site, id })
export const parseInput = (site: Site, text: string) =>
  invoke<Query>('parse_input', { site, text })
export const enqueue = (site: Site, jobs: Job[]) => invoke<void>('enqueue', { site, jobs })
export const pauseQueue = (paused: boolean) => invoke<void>('pause_queue', { paused })
export const cancelQueue = () => invoke<void>('cancel_queue')
export const openFolder = () => invoke<void>('open_folder')
export const cacheStats = () => invoke<CacheStats>('cache_stats')
export const clearCache = () => invoke<void>('clear_cache')

// --- 이벤트 -------------------------------------------------------------

export function onEvent<T>(name: string, cb: (payload: T) => void): Promise<UnlistenFn> {
  return listen<T>(name, (e) => cb(e.payload))
}

// --- img:// -------------------------------------------------------------

/** 이미지 프로토콜 주소. 윈도우의 WebView2 는 사용자 프로토콜을 `http://img.localhost/` 로 부른다. */
export function imgUrl(url: string, ext: string, gen: number, site: Site): string {
  ext = safeExt(ext)
  const base = /Windows/i.test(navigator.userAgent) ? 'http://img.localhost/' : 'img://localhost/'
  return `${base}?u=${encodeURIComponent(url)}&e=${encodeURIComponent(ext)}&g=${gen}&s=${site}`
}

/** 백엔드는 확장자를 ^[A-Za-z0-9]{1,5}$ 로만 받는다. 아니면 "img". */
export function safeExt(ext: string): string {
  return /^[A-Za-z0-9]{1,5}$/.test(ext) ? ext : 'img'
}

/** 주소 경로 끝의 확장자(1~5자 영숫자). 없으면 "img". */
export function extFromUrl(url: string): string {
  let path = url
  try {
    path = new URL(url, 'http://x/').pathname
  } catch {
    // 주소가 아니면 문자열 그대로 본다.
  }
  const m = /\.([A-Za-z0-9]{1,5})$/.exec(path)
  return m ? m[1] : 'img'
}
