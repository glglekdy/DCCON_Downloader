import { writable } from 'svelte/store'

/** 내용 영역 위쪽의 한 줄 알림. 5초 뒤 사라진다. (Task 17 에서 독으로 옮길 수 있다.) */
export const notice = writable<string | null>(null)

let timer: ReturnType<typeof setTimeout> | undefined

export function showNotice(message: string, ms = 5000): void {
  clearTimeout(timer)
  notice.set(message)
  timer = setTimeout(() => notice.set(null), ms)
}

export function dismissNotice(): void {
  clearTimeout(timer)
  notice.set(null)
}
