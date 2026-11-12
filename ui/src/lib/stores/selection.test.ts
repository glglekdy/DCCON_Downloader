import { get } from 'svelte/store'
import { describe, expect, it } from 'vitest'
import { createSelection } from './selection'

describe('createSelection', () => {
  it('setAll, toggle, clear', () => {
    const s = createSelection()
    s.setAll([1, 2, 3], true)
    expect(s.count).toBe(3)
    s.toggle(2)
    expect(s.count).toBe(2)
    expect(s.has(2)).toBe(false)
    expect(s.has(1)).toBe(true)
    s.clear()
    expect(s.count).toBe(0)
  })

  it('setAll(keys,false) 는 그 키만 뺀다', () => {
    const s = createSelection()
    s.setAll([1, 2, 3], true)
    s.setAll([1, 2], false)
    expect(s.count).toBe(1)
    expect(s.has(3)).toBe(true)
  })

  it('스토어로 구독할 수 있고 바뀔 때마다 새 Set 이다', () => {
    const s = createSelection()
    const before = get(s)
    s.toggle(7)
    const after = get(s)
    expect(after).not.toBe(before)
    expect(after.has(7)).toBe(true)
    expect(before.has(7)).toBe(false)
  })
})
