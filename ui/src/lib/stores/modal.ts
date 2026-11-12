import { writable } from 'svelte/store'

/** 열려 있는 모달 id 들. 맨 뒤가 맨 위. Esc 는 맨 위만 닫고, 단축키는 모달이 있으면 쉰다. */
export const modalStack = writable<number[]>([])

let next = 0

export function pushModal(): number {
  const id = ++next
  modalStack.update((s) => [...s, id])
  return id
}

export function popModal(id: number): void {
  modalStack.update((s) => s.filter((i) => i !== id))
}
