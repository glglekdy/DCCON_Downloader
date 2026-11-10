/** 검색 입력창으로 가는 바로가기: 맥은 Meta+L, 나머지는 Ctrl+L. */
export function isFocusSearch(
  e: Pick<KeyboardEvent, 'key' | 'ctrlKey' | 'metaKey' | 'altKey' | 'shiftKey'>,
  mac: boolean = /Mac|iPhone|iPad/i.test(globalThis.navigator?.platform ?? ''),
): boolean {
  if (e.altKey || e.shiftKey || e.key.toLowerCase() !== 'l') return false
  return mac ? e.metaKey && !e.ctrlKey : e.ctrlKey && !e.metaKey
}
