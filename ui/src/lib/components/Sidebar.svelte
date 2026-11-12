<script lang="ts">
  import type { Site } from '../api'
  import icon from '../../assets/icon.png'

  interface Props {
    site: Site
    tab: string | null
    onNavigate?: (site: Site, tab: string) => void
    onSite?: (site: Site) => void
    onHome?: () => void
    onOpenFolder?: () => void
    onOpenSettings?: () => void
  }
  let {
    site,
    tab,
    onNavigate = () => {},
    onSite = () => {},
    onHome = () => {},
    onOpenFolder = () => {},
    onOpenSettings = () => {},
  }: Props = $props()

  const SITES: [Site, string][] = [
    ['dccon', '디시콘'],
    ['arca', '아카콘'],
  ]
  const SECTIONS: Record<Site, { title: string; tabs: [string, string][] }[]> = {
    dccon: [
      {
        title: '인기',
        tabs: [
          ['day', '일간 인기'],
          ['week', '주간 인기'],
          ['month', '월간 인기'],
        ],
      },
      {
        title: '둘러보기',
        tabs: [
          ['official', '공식'],
          ['all', '전체 목록'],
        ],
      },
    ],
    arca: [
      {
        title: '아카콘',
        tabs: [
          ['new', '최신'],
          ['weekly', '주간 인기'],
          ['monthly', '월간 인기'],
        ],
      },
    ],
  }
</script>

<aside class="sidebar">
  <button type="button" class="brand-row" title="홈으로" aria-label="홈으로" onclick={onHome}>
    <img src={icon} alt="" width="28" height="28" />
    <span class="brand">dccon</span>
  </button>

  <div class="segment">
    {#each SITES as [key, label] (key)}
      <button
        type="button"
        class="seg-button"
        class:checked={site === key}
        aria-pressed={site === key}
        onclick={() => onSite(key)}>{label}</button
      >
    {/each}
  </div>

  <nav>
    {#each SECTIONS[site] as section (section.title)}
      <div class="nav-section">{section.title}</div>
      {#each section.tabs as [key, label] (key)}
        <button
          type="button"
          class="nav-item"
          class:checked={tab === key}
          aria-current={tab === key ? 'page' : undefined}
          onclick={() => onNavigate(site, key)}>{label}</button
        >
      {/each}
    {/each}
  </nav>

  <div class="stretch"></div>
  <button type="button" class="nav-item" onclick={onOpenFolder}>폴더 열기</button>
  <button type="button" class="nav-item" onclick={onOpenSettings}>설정</button>
</aside>

<style>
  .sidebar {
    width: 210px;
    flex: none;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    gap: 2px;
    /* QFrame 의 스타일시트 테두리는 레이아웃 여백을 줄이지 않는다: 안쪽 폭 186 (1.3.0) */
    padding: 16px 11px 16px 12px;
    background: var(--surface);
    border-right: 1px solid var(--topbar-border);
  }
  .brand-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 0 0 14px 6px;
    background: transparent;
    text-align: left;
    min-height: 0;
    border-radius: 0;
  }
  .brand-row:hover {
    background: transparent;
  }
  .brand-row img {
    display: block;
  }
  .brand {
    color: var(--text);
    font-size: 16px;
    font-weight: 700;
  }
  .segment {
    display: flex;
    gap: 2px;
    padding: 3px;
    margin-bottom: 10px;
    background: var(--input-bg);
    border-radius: 6px;
  }
  .seg-button {
    flex: 1;
    background: transparent;
    color: var(--muted);
    border-radius: 4px;
    padding: 5px 0;
    min-height: 14px;
  }
  .seg-button:hover {
    background: transparent;
    color: var(--text);
  }
  .seg-button.checked {
    background: var(--btn-hover-bg);
    color: var(--text);
  }
  nav {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .nav-section {
    color: var(--muted);
    font-size: 11px;
    padding: 10px 8px 4px;
  }
  .nav-item {
    background: transparent;
    color: var(--muted);
    text-align: left;
    font-weight: 400;
    border: none;
    border-left: 3px solid transparent;
    border-radius: 6px;
    padding: 8px 10px;
    min-height: 16px;
  }
  .nav-item:hover {
    background: var(--tab-hover);
    color: var(--text);
  }
  .nav-item.checked {
    background: var(--tab-checked-bg);
    border-left-color: var(--accent);
    color: var(--text);
    font-weight: 500;
  }
  .stretch {
    flex: 1;
  }
</style>
