import { get } from 'svelte/store'
import { describe, expect, it } from 'vitest'
import type { Brief, Package } from '../api'
import { createQueue, jobsFor, statusLine } from './queue'

const two = [
  { id: 1, title: '하나' },
  { id: 2, title: '둘' },
]

describe('createQueue', () => {
  it('두 작업의 진행을 합산한다', () => {
    const q = createQueue()
    q.onStarted({ jobs: two })
    expect(get(q).running).toBe(true)
    expect(get(q).jobs.size).toBe(2)
    q.onProgress({ id: 1, done: 2, total: 4, name: 'a.png' })
    q.onProgress({ id: 2, done: 1, total: 2, name: 'b.png' })
    expect(get(q).overall).toEqual({ done: 3, total: 6 })
    expect(get(q).jobs.get(1)).toMatchObject({ done: 2, total: 4, name: 'a.png' })
  })

  it('패키지 완료 문구는 0 인 항목을 생략하고 두 칸 띄운다', () => {
    const q = createQueue()
    q.onStarted({ jobs: two })
    q.onPackageDone({ id: 1, title: '하나', saved: 3, skipped: 1, failed: [] })
    expect(get(q).jobs.get(1)?.status).toBe('저장 3  건너뜀 1')
    q.onPackageDone({ id: 2, title: '둘', saved: 0, skipped: 0, failed: [['x', 'y']] })
    expect(get(q).jobs.get(2)?.status).toBe('저장 0  실패 1')
  })

  it('오류는 해당 작업에 적는다', () => {
    const q = createQueue()
    q.onStarted({ jobs: two })
    q.onError({ id: 2, message: '망함' })
    expect(get(q).jobs.get(2)?.status).toBe('오류: 망함')
  })

  it('끝나면 요약을 남기고 dismiss 로 지운다', () => {
    const q = createQueue()
    q.onStarted({ jobs: two })
    q.onFinished({ saved: 5, skipped: 0, failed: 2 })
    expect(get(q).running).toBe(false)
    expect(get(q).summary).toBe('완료 · 저장 5개, 실패 2개')
    q.dismiss()
    expect(get(q).summary).toBeNull()
    expect(get(q).jobs.size).toBe(0)
  })

  it('요약에는 건너뜀도 들어간다', () => {
    const q = createQueue()
    q.onStarted({ jobs: two })
    q.onFinished({ saved: 1, skipped: 4, failed: 0 })
    expect(get(q).summary).toBe('완료 · 저장 1개, 건너뜀 4개')
  })

  it('중단하면 바로 "중단하는 중…" 이 되고 끝나면 풀린다', () => {
    const q = createQueue()
    q.onStarted({ jobs: two })
    q.setPaused(true)
    expect(get(q).paused).toBe(true)
    q.markCancelling()
    expect(statusLine(get(q))).toBe('중단하는 중…')
    q.onFinished({ saved: 0, skipped: 0, failed: 0 })
    expect(get(q).cancelling).toBe(false)
    expect(get(q).paused).toBe(false)
    expect(statusLine(get(q))).toBe('완료 · 저장 0개')
  })

  it('상태 줄: 시작 직후 / 진행 중', () => {
    const q = createQueue()
    q.onStarted({ jobs: two })
    expect(statusLine(get(q))).toBe('2개 패키지 받는 중')
    q.onProgress({ id: 1, done: 1, total: 4, name: '' })
    expect(statusLine(get(q))).toBe('1 / 4개 받는 중')
  })
})

describe('jobsFor', () => {
  const rows = [
    { idx: 10, title: 'a', seller: '', thumb_url: '' },
    { idx: 11, title: 'b', seller: '', thumb_url: '' },
    { idx: 12, title: 'c', seller: '', thumb_url: '' },
  ] as Brief[]
  const pkg = {
    idx: 7,
    title: '팩',
    items: [
      { sort: 1 },
      { sort: 2 },
      { sort: 3 },
    ],
  } as unknown as Package

  it('목록: 고른 패키지마다 sorts null', () => {
    expect(jobsFor({ pkg: null, rows }, new Set([12, 10]))).toEqual([
      { id: 10, title: 'a', sorts: null },
      { id: 12, title: 'c', sorts: null },
    ])
  })
  it('패키지: 한 건에 고른 sort', () => {
    expect(jobsFor({ pkg, rows: [] }, new Set([3, 1]))).toEqual([
      { id: 7, title: '팩', sorts: [1, 3] },
    ])
  })
  it('고른 게 없으면 빈 배열', () => {
    expect(jobsFor({ pkg, rows: [] }, new Set())).toEqual([])
  })
})

describe('clearCancelling', () => {
  it('중단 요청이 실패하면 중단하는 중 상태를 되돌린다', () => {
    const q = createQueue()
    q.onStarted({ jobs: two })
    q.markCancelling()
    expect(get(q).cancelling).toBe(true)
    q.clearCancelling()
    expect(get(q).cancelling).toBe(false)
    expect(get(q).running).toBe(true)
  })
})
