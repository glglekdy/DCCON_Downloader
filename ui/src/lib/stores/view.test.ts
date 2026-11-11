import { get } from 'svelte/store'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../api', async (orig) => {
  const real = await orig<typeof import('../api')>()
  const brief = (idx: number, title: string) => ({ idx, title, seller: '', thumb_url: '' })
  const item = (sort: number, title: string) => ({
    idx: sort,
    title,
    sort,
    ext: 'png',
    path: `p${sort}`,
    thumb: '',
  })
  return {
    ...real,
    beginView: vi.fn(async () => 1),
    listAll: vi.fn(async (page: number) => ({
      items: [brief(5, 'a'), brief(0, 'b'), brief(5, 'c'), brief(0, 'd')],
      page,
      pages: 1,
      total: null,
    })),
    openPackage: vi.fn(async (_site: string, id: number) => ({
      idx: id,
      title: 't',
      seller: '',
      items: [item(1, 'x'), item(2, 'y'), item(1, 'z')],
    })),
  }
})

const { showView, viewState } = await import('./view')

describe('showView', () => {
  it('목록에서 겹치는 idx 는 처음 것만 남긴다', async () => {
    await showView({ kind: 'all', page: 1 })
    const s = get(viewState)
    expect(s.rows.map((r) => r.title)).toEqual(['a', 'b'])
    expect(s.resultText).toBe('2개 패키지')
  })

  it('패키지에서 겹치는 sort 는 처음 것만 남긴다', async () => {
    await showView({ kind: 'package', site: 'dccon', id: 9 })
    expect(get(viewState).pkg?.items.map((i) => i.title)).toEqual(['x', 'y'])
  })
})
