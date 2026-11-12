import { describe, expect, it } from 'vitest'
import { isFocusSearch } from './shortcuts'

const key = (o: Partial<KeyboardEvent>) => ({
  key: 'l',
  ctrlKey: false,
  metaKey: false,
  altKey: false,
  shiftKey: false,
  ...o,
})

describe('isFocusSearch', () => {
  it('윈도우·리눅스는 Ctrl+L', () => {
    expect(isFocusSearch(key({ ctrlKey: true }), false)).toBe(true)
    expect(isFocusSearch(key({ ctrlKey: true, key: 'L' }), false)).toBe(true)
    expect(isFocusSearch(key({ metaKey: true }), false)).toBe(false)
    expect(isFocusSearch(key({}), false)).toBe(false)
  })
  it('맥은 Meta+L', () => {
    expect(isFocusSearch(key({ metaKey: true }), true)).toBe(true)
    expect(isFocusSearch(key({ ctrlKey: true }), true)).toBe(false)
  })
  it('다른 조합은 아니다', () => {
    expect(isFocusSearch(key({ ctrlKey: true, shiftKey: true }), false)).toBe(false)
    expect(isFocusSearch(key({ ctrlKey: true, key: 'k' }), false)).toBe(false)
  })
})
