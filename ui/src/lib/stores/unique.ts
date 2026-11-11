/**
 * 키가 겹치는 항목은 처음 것만 남긴다. 그리드의 keyed `{#each}` 는 키가 겹치면
 * 운영 빌드에서도 예외를 던져 화면이 비므로, 서버가 같은 번호를 두 번 줘도 넘어가게 한다.
 */
export function uniqueBy<T, K>(items: readonly T[], key: (item: T) => K): T[] {
  const seen = new Set<K>()
  const out: T[] = []
  for (const item of items) {
    const k = key(item)
    if (seen.has(k)) continue
    seen.add(k)
    out.push(item)
  }
  return out
}
