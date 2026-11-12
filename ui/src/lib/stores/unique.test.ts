import { describe, expect, it } from 'vitest'
import { uniqueBy } from './unique'

describe('uniqueBy', () => {
  it('겹치는 키는 처음 것만 남기고 순서를 지킨다', () => {
    const rows = [
      { idx: 3, title: 'a' },
      { idx: 0, title: 'b' },
      { idx: 3, title: 'c' },
      { idx: 0, title: 'd' },
      { idx: 7, title: 'e' },
    ]
    expect(uniqueBy(rows, (r) => r.idx).map((r) => r.title)).toEqual(['a', 'b', 'e'])
  })

  it('겹치지 않으면 그대로', () => {
    const items = [{ sort: 1 }, { sort: 2 }]
    expect(uniqueBy(items, (i) => i.sort)).toEqual(items)
  })
})
