import { tick } from 'svelte'
import { get, writable } from 'svelte/store'
import {
  beginView,
  isCmdError,
  listAll,
  listArca,
  listTop,
  openPackage,
  search,
  type Brief,
  type Package,
  type Site,
} from '../api'
import { createHistory } from './history'
import { activeTab, currentSite, loading } from './nav'
import { createSelection } from './selection'
import type { View } from './view-types'

export type { ArcaTab, HomeTab, View } from './view-types'

export interface ViewState {
  view: View | null
  site: Site
  /** begin_view 가 준 세대. 이미지 요청에 실어 보낸다. */
  gen: number
  crumb: string
  hint: string
  resultText: string
  rows: Brief[]
  pkg: Package | null
  page: number
  pages: number
  /** 이전·다음 쪽 버튼을 보일지. */
  paged: boolean
  /** 가운데 안내(빈 결과·오류). */
  notice: string | null
}

const EMPTY: ViewState = {
  view: null,
  site: 'dccon',
  gen: 0,
  crumb: '',
  hint: '',
  resultText: '',
  rows: [],
  pkg: null,
  page: 1,
  pages: 1,
  paged: false,
  notice: null,
}

export const viewState = writable<ViewState>(EMPTY)
export const navState = writable({ canBack: false, canForward: false })
/** Task 19 가 로그인 창을 띄우는 신호. */
export const loginNeeded = writable(false)
export const selection = createSelection()

const HOME_LABEL = { day: '일간 인기', week: '주간 인기', month: '월간 인기', official: '공식' }
const ARCA_LABEL = { new: '최신', weekly: '주간 인기', monthly: '월간 인기' }
export const PACKAGE_HINT = '저장할 디시콘을 선택한 뒤 다운로드하세요.'

const hist = createHistory()
let seq = 0
let current: View | null = null
/** 지금 화면의 불러오기가 끝났는가. 끝나기 전에는 스크롤 위치를 기록하지 않는다. */
let settled = false
// begin_view 를 부른 순서대로 세대를 받는다.
let begun: Promise<unknown> = Promise.resolve()
function nextGeneration(): Promise<number> {
  const p = begun.then(() => beginView(), () => beginView())
  begun = p.catch(() => undefined)
  return p
}

function scrollNow(): number | undefined {
  return settled ? scroller.get() : undefined
}

/** 사이트를 바꿀 때 이동 기록을 비운다. */
export function resetHistory(): void {
  hist.clear()
  syncNav()
}

/** 콘텐츠 스크롤 컨테이너를 App 이 등록한다. */
const scroller = { get: (): number => 0, set: (_y: number): void => {} }
export function setScroller(getY: () => number, setY: (y: number) => void) {
  scroller.get = getY
  scroller.set = setY
}

function syncNav() {
  navState.set({ canBack: hist.canBack, canForward: hist.canForward })
}

function viewSite(v: View): Site {
  if (v.kind === 'arca') return 'arca'
  if (v.kind === 'search' || v.kind === 'package') return v.site
  return 'dccon'
}

function crumbOf(v: View): string {
  switch (v.kind) {
    case 'top':
      return `${HOME_LABEL[v.tab]} 디시콘`
    case 'all':
      return '전체 디시콘'
    case 'arca':
      return `${ARCA_LABEL[v.tab]} 아카콘`
    case 'search':
      return `“${v.word}” 검색 결과`
    case 'package':
      return '불러오는 중…'
  }
}

function tabOf(v: View): string | null {
  if (v.kind === 'top') return v.tab
  if (v.kind === 'all') return 'all'
  if (v.kind === 'arca') return v.tab
  return null
}

function emptyMessage(v: View): string {
  switch (v.kind) {
    case 'top':
      return '아직 표시할 패키지가 없습니다. 다른 인기 목록이나 검색을 이용해 보세요.'
    case 'all':
      return '이 페이지에는 디시콘이 없습니다.'
    case 'arca':
      return '이 페이지에는 아카콘이 없습니다.'
    case 'search':
      return `“${v.word}” 검색 결과가 없습니다.`
    case 'package':
      return '이 패키지에는 디시콘이 없습니다.'
  }
}

export async function showView(
  v: View,
  opts: { record?: boolean; scrollY?: number } = {},
): Promise<void> {
  const record = opts.record ?? true
  const mine = ++seq
  if (record) {
    // 패키지는 목록·검색에서 열 때만 기록한다 (이미 패키지를 보고 있으면 제자리 교체).
    if (v.kind === 'package' && current && current.kind !== 'package') hist.push(v, scrollNow())
    else hist.replace(v)
  }
  syncNav()
  current = v
  settled = false
  const site = viewSite(v)
  currentSite.set(site)
  activeTab.set(tabOf(v))
  loading.set(true)
  selection.clear()
  // 쪽 번호 줄은 쪽을 넘길 때마다 사라졌다 나타나지 않도록 로딩 중에도 둔다 (Heading 이 비활성으로 보인다).
  const prev = get(viewState)
  const pagedKind = 'page' in v
  viewState.set({
    ...EMPTY,
    view: v,
    site,
    crumb: crumbOf(v),
    hint: v.kind === 'package' ? PACKAGE_HINT : '',
    paged: pagedKind,
    page: pagedKind ? v.page : 1,
    pages: pagedKind ? (prev.paged ? Math.max(prev.pages, v.page) : v.page) : 1,
  })
  scroller.set(0)

  try {
    const gen = await nextGeneration()
    if (mine !== seq) return

    if (v.kind === 'package') {
      const pkg = await openPackage(v.site, v.id)
      if (mine !== seq) return
      let sub = `${pkg.items.length}개`
      if (pkg.seller) sub += ` · ${pkg.seller}`
      selection.setAll(
        pkg.items.map((i) => i.sort),
        true,
      )
      viewState.update((s) => ({
        ...s,
        gen,
        pkg,
        crumb: pkg.title,
        hint: `${sub} · 저장할 디시콘을 선택하세요.`,
        notice: pkg.items.length ? null : emptyMessage(v),
      }))
    } else {
      const res =
        v.kind === 'top'
          ? await listTop(v.tab)
          : v.kind === 'all'
            ? await listAll(v.page)
            : v.kind === 'arca'
              ? await listArca(v.tab, v.page)
              : await search(v.site, v.word, v.type, v.page)
      if (mine !== seq) return
      viewState.update((s) => ({
        ...s,
        gen,
        paged: v.kind === 'all' || v.kind === 'arca' || v.kind === 'search',
        rows: res.items,
        page: res.page,
        pages: Math.max(res.pages, res.page),
        resultText:
          v.kind === 'all' && res.total
            ? `총 ${res.total.toLocaleString('en-US')}개`
            : res.items.length
              ? `${res.items.length}개 패키지`
              : '',
        notice: res.items.length ? null : emptyMessage(v),
      }))
    }
    await tick()
    if (mine === seq) settled = true
    if (mine === seq) scroller.set(opts.scrollY ?? 0)
  } catch (e) {
    if (mine !== seq) return
    settled = true
    if (isCmdError(e) && e.kind === 'cancelled') return
    if (isCmdError(e) && e.kind === 'login_required') {
      loginNeeded.set(true)
      viewState.update((s) => ({ ...s, paged: false, notice: '아카라이브 로그인이 만료되었습니다.' }))
    } else {
      const message = isCmdError(e) ? e.message : String(e)
      viewState.update((s) => ({ ...s, paged: false, notice: `불러오지 못했습니다.\n${message}` }))
    }
  } finally {
    if (mine === seq) loading.set(false)
  }
}

export function goBack(): void {
  const e = hist.back(scrollNow())
  if (e) void showView(e.view, { record: false, scrollY: e.scrollY })
}

export function goForward(): void {
  const e = hist.forward(scrollNow())
  if (e) void showView(e.view, { record: false, scrollY: e.scrollY })
}

/** 쪽 번호를 바꿀 수 있는 화면이면 그 쪽으로. */
export function goPage(target: number): void {
  const v = current
  if (!v || !('page' in v)) return
  const { pages } = get(viewState)
  const page = Math.max(1, Math.min(pages, target))
  if (page !== v.page) void showView({ ...v, page })
}

export function stepPage(delta: number): void {
  const v = current
  if (v && 'page' in v) goPage(get(viewState).page + delta)
}
