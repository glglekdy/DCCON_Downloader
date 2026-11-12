import { describe, expect, it } from 'vitest'
import { createHistory } from './history'
import type { View } from './view-types'

const top = (tab: 'day' | 'week'): View => ({ kind: 'top', tab })
const A = top('day')
const B: View = { kind: 'all', page: 37 }
const C: View = { kind: 'package', site: 'dccon', id: 5 }
const D: View = { kind: 'search', site: 'dccon', word: '멍뭉', type: 'title', page: 1 }

describe('createHistory', () => {
  it('push A,B,C 후 back 은 B, back 은 A, forward 는 B', () => {
    const h = createHistory()
    h.push(A, 0)
    h.push(B, 0)
    h.push(C, 0)
    expect(h.back(0)?.view).toEqual(B)
    expect(h.back(0)?.view).toEqual(A)
    expect(h.back(0)).toBeNull()
    expect(h.forward(0)?.view).toEqual(B)
  })

  it('중간에서 push 하면 앞쪽 기록이 사라진다', () => {
    const h = createHistory()
    h.push(A, 0)
    h.push(B, 0)
    h.push(C, 0)
    h.back(0)
    h.back(0)
    h.forward(0)
    expect(h.canForward).toBe(true)
    h.push(D, 0)
    expect(h.canForward).toBe(false)
    expect(h.forward(0)).toBeNull()
    expect(h.back(0)?.view).toEqual(B)
  })

  it('떠나는 화면의 스크롤 위치가 돌아올 때 함께 온다', () => {
    const h = createHistory()
    h.push(B, 0)
    h.push(C, 480) // B 를 480 까지 내린 채 C 로 감
    const back = h.back(75) // C 를 75 까지 내린 채 B 로 돌아옴
    expect(back).toEqual({ view: B, scrollY: 480 })
    expect(h.forward(480)).toEqual({ view: C, scrollY: 75 })
  })

  it('canBack/canForward', () => {
    const h = createHistory()
    expect(h.canBack).toBe(false)
    h.push(A, 0)
    expect(h.canBack).toBe(false)
    h.push(B, 0)
    expect(h.canBack).toBe(true)
    expect(h.canForward).toBe(false)
    h.back(0)
    expect(h.canBack).toBe(false)
    expect(h.canForward).toBe(true)
  })

  it('replace 는 현재 항목만 바꾸고 앞쪽 기록은 둔다', () => {
    const h = createHistory()
    h.push(A, 0)
    h.push(B, 0)
    h.back(0)
    h.replace(top('week'))
    expect(h.canForward).toBe(true)
    expect(h.canBack).toBe(false)
    expect(h.forward(0)?.view).toEqual(B)
  })

  it('스크롤을 안 주면 저장된 위치를 덮어쓰지 않는다', () => {
    const h = createHistory()
    h.push(B, 0)
    h.push(C, 300)
    h.back(40)
    h.forward() // 40 은 C 에 저장됨, B 는 300 그대로
    expect(h.back()?.scrollY).toBe(300)
    expect(h.forward()?.scrollY).toBe(40)
  })

  it('clear', () => {
    const h = createHistory()
    h.push(A, 0)
    h.push(B, 0)
    h.clear()
    expect(h.canBack).toBe(false)
    expect(h.canForward).toBe(false)
  })
})
