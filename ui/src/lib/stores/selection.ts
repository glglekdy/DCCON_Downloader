import { writable, get, type Readable } from 'svelte/store'

export interface Selection extends Readable<Set<number>> {
  toggle(key: number): void
  setAll(keys: Iterable<number>, on: boolean): void
  clear(): void
  has(key: number): boolean
  readonly count: number
}

/** 고른 카드의 키 모음. 목록에서는 패키지 번호, 패키지 안에서는 sort. */
export function createSelection(): Selection {
  const store = writable<Set<number>>(new Set())
  return {
    subscribe: store.subscribe,
    toggle: (key) =>
      store.update((s) => {
        const next = new Set(s)
        if (!next.delete(key)) next.add(key)
        return next
      }),
    setAll: (keys, on) =>
      store.update((s) => {
        const next = new Set(s)
        for (const k of keys) {
          if (on) next.add(k)
          else next.delete(k)
        }
        return next
      }),
    clear: () => store.set(new Set()),
    has: (key) => get(store).has(key),
    get count() {
      return get(store).size
    },
  }
}
