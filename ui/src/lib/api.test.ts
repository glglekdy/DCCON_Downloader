import { afterEach, describe, expect, it, vi } from 'vitest'
import { imgUrl } from './api'

function fakeUserAgent(ua: string) {
  vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue(ua)
}

describe('imgUrl', () => {
  afterEach(() => vi.restoreAllMocks())

  it('윈도우에서는 http://img.localhost/ 를 쓴다', () => {
    fakeUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) Edg/120')
    expect(imgUrl('https://a/b.gif', 'gif', 3, 'dccon')).toBe(
      'http://img.localhost/?u=https%3A%2F%2Fa%2Fb.gif&e=gif&g=3&s=dccon',
    )
  })

  it('그 밖에서는 img://localhost/ 를 쓴다', () => {
    fakeUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15')
    expect(imgUrl('https://a/b.gif', 'gif', 3, 'arca')).toBe(
      'img://localhost/?u=https%3A%2F%2Fa%2Fb.gif&e=gif&g=3&s=arca',
    )
  })
})

describe('ext 보호', () => {
  it('extFromUrl', async () => {
    const { extFromUrl, safeExt } = await import('./api')
    expect(extFromUrl('https://a/b/c.PNG?x=1')).toBe('PNG')
    expect(extFromUrl('https://a/b/c')).toBe('img')
    expect(extFromUrl('https://a/b/c.toolong')).toBe('img')
    expect(safeExt('gi/f')).toBe('img')
    expect(safeExt('gif')).toBe('gif')
  })
})
