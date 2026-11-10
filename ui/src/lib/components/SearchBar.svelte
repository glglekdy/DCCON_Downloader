<script lang="ts">
  import type { Site } from '../api'

  let {
    site,
    onSubmit = () => {},
  }: { site: Site; onSubmit?: (text: string, searchType: string) => void } = $props()

  let input: HTMLInputElement | undefined = $state()

  /** 바로가기(Ctrl+L)가 입력창으로 옮겨올 때 쓴다. */
  export function focus() {
    input?.focus()
    input?.select()
  }

  const TYPES: Record<Site, [string, string][]> = {
    dccon: [
      ['title', '제목'],
      ['nick_name', '작가'],
      ['tags', '태그'],
    ],
    arca: [
      ['title', '제목'],
      ['nickname', '작가'],
      ['tag', '태그'],
    ],
  }

  let searchType = $state('title')
  let word = $state('')
  const options = $derived(TYPES[site])

  // 사이트가 바뀌면 종류 키가 달라지므로 제목으로 되돌린다.
  $effect(() => {
    void site
    searchType = 'title'
  })

  function submit(e: Event) {
    e.preventDefault()
    onSubmit(word, searchType)
  }
</script>

<form class="search-bar" onsubmit={submit}>
  <select bind:value={searchType} aria-label="검색 종류">
    {#each options as [key, label] (key)}
      <option value={key}>{label}</option>
    {/each}
  </select>
  <div class="omnibox">
    <input
      type="text"
      bind:value={word}
      bind:this={input}
      placeholder={site === 'arca'
        ? '검색어, 아카콘 번호 또는 arca.live/e/ 주소'
        : '검색어, 패키지 ID 또는 디시콘 URL'}
      aria-label="검색"
      title="검색어, 패키지 ID 또는 URL을 입력하고 Enter. Ctrl+L로 바로 이동"
    />
    {#if word}
      <button type="button" class="clear" aria-label="지우기" onclick={() => (word = '')}>
        <!-- QLineEdit 지우기 단추: 14px 회색 원 안의 흰 × (테마와 상관없이 같은 색) -->
        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
          <circle cx="7" cy="7" r="7" fill="#4d4d4d" />
          <path d="M4.5 4.5l5 5M9.5 4.5l-5 5" stroke="#fff" stroke-width="1.5" stroke-linecap="round" />
        </svg>
      </button>
    {/if}
  </div>
</form>

<style>
  .search-bar {
    display: flex;
    gap: 8px;
    padding: 14px 22px 6px;
    background: var(--bg);
  }
  select {
    min-width: 76px;
  }
  .omnibox {
    position: relative;
    flex: 1;
    min-width: 180px;
    display: flex;
  }
  .omnibox input {
    flex: 1;
    padding-right: 28px;
  }
  .clear {
    position: absolute;
    right: 4px;
    top: 50%;
    transform: translateY(-50%);
    width: 22px;
    height: 18px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    padding: 0;
    min-height: 0;
  }
  .clear:hover {
    background: transparent;
  }
  .clear svg {
    display: block;
  }
</style>
