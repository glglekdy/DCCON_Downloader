import { writable } from 'svelte/store'
import type { Site } from '../api'

export const currentSite = writable<Site>('dccon')
/** 사이드바에서 눌린 메뉴. 디시콘: day/week/month/official/all, 아카콘: new/weekly/monthly. null 이면 홈이 아닌 화면. */
export const activeTab = writable<string | null>('day')
/** 화면 위쪽 2px 로딩 줄. */
export const loading = writable(false)
