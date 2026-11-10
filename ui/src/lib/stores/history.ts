// 이동 기록. DOM 을 모르는 순수 모듈이라 단위 시험이 된다.
import type { View } from './view-types'

export interface Entry {
  view: View
  scrollY: number
}

export interface History {
  /** 새 화면으로 간다. scrollY 는 지금 떠나는 화면의 스크롤 위치. 앞쪽 기록은 지워진다. */
  push(view: View, scrollY: number): void
  /** 지금 항목을 바꾼다(쪽 넘김·탭 전환). 앞쪽 기록은 지워진다. */
  replace(view: View): void
  /** scrollY 는 지금 떠나는 화면의 스크롤 위치. 돌아갈 곳이 없으면 null. */
  back(scrollY?: number): Entry | null
  forward(scrollY?: number): Entry | null
  readonly canBack: boolean
  readonly canForward: boolean
}

export function createHistory(): History {
  const entries: Entry[] = []
  let index = -1

  return {
    push(view, scrollY) {
      if (index >= 0) entries[index].scrollY = scrollY
      entries.length = index + 1
      entries.push({ view, scrollY: 0 })
      index = entries.length - 1
    },
    replace(view) {
      if (index < 0) {
        entries.push({ view, scrollY: 0 })
        index = 0
        return
      }
      entries.length = index + 1
      entries[index] = { view, scrollY: 0 }
    },
    back(scrollY = 0) {
      if (index <= 0) return null
      entries[index].scrollY = scrollY
      index -= 1
      return { ...entries[index] }
    },
    forward(scrollY = 0) {
      if (index < 0 || index >= entries.length - 1) return null
      entries[index].scrollY = scrollY
      index += 1
      return { ...entries[index] }
    },
    get canBack() {
      return index > 0
    },
    get canForward() {
      return index >= 0 && index < entries.length - 1
    },
  }
}
