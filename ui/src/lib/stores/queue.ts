import { writable, type Readable } from 'svelte/store'
import type { Brief, Job, Package } from '../api'

export interface QueueJob {
  title: string
  done: number
  total: number
  name: string
  /** 끝난 뒤의 문구(`저장 3  건너뜀 1`, `오류: …`). 아직이면 null. */
  status: string | null
}

export interface QueueState {
  running: boolean
  paused: boolean
  /** 중단을 눌렀고 마지막 소식(queue-finished)을 기다리는 중. */
  cancelling: boolean
  jobs: Map<number, QueueJob>
  overall: { done: number; total: number }
  /** 끝난 뒤의 한 줄 요약. 닫기(dismiss) 전까지 남는다. */
  summary: string | null
}

export interface Queue extends Readable<QueueState> {
  onStarted(p: { jobs: { id: number; title: string }[] }): void
  onProgress(p: { id: number; done: number; total: number; name: string }): void
  onPackageDone(p: {
    id: number
    title: string
    saved: number
    skipped: number
    failed: unknown[]
  }): void
  onError(p: { id: number; message: string }): void
  onFinished(p: { saved: number; skipped: number; failed: number }): void
  setPaused(paused: boolean): void
  markCancelling(): void
  /** 중단 요청이 실패했을 때 "중단하는 중…" 을 되돌린다. */
  clearCancelling(): void
  dismiss(): void
}

const IDLE = (): QueueState => ({
  running: false,
  paused: false,
  cancelling: false,
  jobs: new Map(),
  overall: { done: 0, total: 0 },
  summary: null,
})

function overallOf(jobs: Map<number, QueueJob>) {
  let done = 0
  let total = 0
  for (const j of jobs.values()) {
    done += j.done
    total += j.total
  }
  return { done, total }
}

/** 큐 진행 상태. 백엔드 이벤트를 받아 적기만 한다 (화면과 무관). */
export function createQueue(): Queue {
  const store = writable<QueueState>(IDLE())

  /** 한 작업만 바꾼 새 상태를 만든다. 모르는 id 면 그대로. */
  function patch(id: number, change: Partial<QueueJob>) {
    store.update((s) => {
      const job = s.jobs.get(id)
      if (!job) return s
      const jobs = new Map(s.jobs)
      jobs.set(id, { ...job, ...change })
      return { ...s, jobs, overall: overallOf(jobs) }
    })
  }

  return {
    subscribe: store.subscribe,
    onStarted: ({ jobs }) =>
      store.set({
        ...IDLE(),
        running: true,
        jobs: new Map(
          jobs.map((j) => [j.id, { title: j.title, done: 0, total: 0, name: '', status: null }]),
        ),
      }),
    onProgress: ({ id, done, total, name }) => patch(id, { done, total, name }),
    onPackageDone: ({ id, saved, skipped, failed }) => {
      const parts = [`저장 ${saved}`]
      if (skipped) parts.push(`건너뜀 ${skipped}`)
      if (failed.length) parts.push(`실패 ${failed.length}`)
      patch(id, { status: parts.join('  ') })
    },
    onError: ({ id, message }) => patch(id, { status: `오류: ${message}` }),
    onFinished: ({ saved, skipped, failed }) => {
      let summary = `완료 · 저장 ${saved}개`
      if (skipped) summary += `, 건너뜀 ${skipped}개`
      if (failed) summary += `, 실패 ${failed}개`
      store.update((s) => ({ ...s, running: false, paused: false, cancelling: false, summary }))
    },
    setPaused: (paused) => store.update((s) => ({ ...s, paused })),
    markCancelling: () => store.update((s) => (s.running ? { ...s, cancelling: true } : s)),
    clearCancelling: () => store.update((s) => (s.cancelling ? { ...s, cancelling: false } : s)),
    dismiss: () => store.set(IDLE()),
  }
}

export const queue = createQueue()

/** 독 진행 줄의 왼쪽 문구 (`queuebar.py` 의 start / set_overall / finish / set_idle). */
export function statusLine(s: QueueState): string {
  if (s.summary !== null) return s.summary
  if (s.cancelling) return '중단하는 중…'
  if (s.overall.total === 0) return `${s.jobs.size}개 패키지 받는 중`
  return `${s.overall.done} / ${s.overall.total}개 받는 중`
}

/** 전체 진행률(정수 %). 끝났으면 100. */
export function percentOf(s: QueueState): number {
  if (s.summary !== null) return 100
  const { done, total } = s.overall
  return total ? Math.floor((done * 100) / total) : 0
}

/** 패키지별 내역의 두 번째 칸. */
export function rowText(j: QueueJob): string {
  if (j.status !== null) return j.status
  if (j.total === 0) return '대기'
  return `${j.done}/${j.total}` + (j.name ? `  ${j.name}` : '')
}

/** 지금 화면과 고른 키로 enqueue 에 넘길 작업을 만든다. 패키지 안이면 한 건, 목록이면 패키지마다. */
export function jobsFor(
  view: { pkg: Package | null; rows: Brief[] },
  selected: ReadonlySet<number>,
): Job[] {
  if (view.pkg) {
    const sorts = view.pkg.items.filter((i) => selected.has(i.sort)).map((i) => i.sort)
    return sorts.length ? [{ id: view.pkg.idx, title: view.pkg.title, sorts }] : []
  }
  return view.rows
    .filter((b) => selected.has(b.idx))
    .map((b) => ({ id: b.idx, title: b.title, sorts: null }))
}

/** 독을 접어 손잡이만 남겼는지. 받기를 시작하면 App 이 다시 펼친다. */
export const dockHidden = writable(false)
