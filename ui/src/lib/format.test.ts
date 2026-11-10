import { describe, expect, it } from 'vitest'
import { humanSize } from './format'

describe('humanSize', () => {
  it('파이썬판 human_size 와 같은 문구', () => {
    expect(humanSize(0)).toBe('0 B')
    expect(humanSize(1023)).toBe('1,023 B')
    expect(humanSize(1536)).toBe('1.5 KB')
    expect(humanSize(5 * 1048576)).toBe('5.0 MB')
    expect(humanSize(3 * 1024 ** 3)).toBe('3.0 GB')
  })
})
