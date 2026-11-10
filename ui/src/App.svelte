<script lang="ts">
  import { onMount } from 'svelte'
  import { enqueue, isCmdError, openFolder, parseInput, type Site } from './lib/api'
  import Dock from './lib/components/Dock.svelte'
  import Glow from './lib/components/Glow.svelte'
  import Grid from './lib/components/Grid.svelte'
  import Heading from './lib/components/Heading.svelte'
  import LoadingLine from './lib/components/LoadingLine.svelte'
  import SearchBar from './lib/components/SearchBar.svelte'
  import Sidebar from './lib/components/Sidebar.svelte'
  import { activeTab, currentSite, loading } from './lib/stores/nav'
  import { dismissNotice, notice, showNotice } from './lib/stores/notice'
  import { queue } from './lib/stores/queue'
  import { wireQueueEvents } from './lib/stores/queue-events'
  import { loadSettings } from './lib/stores/settings'
  import {
    goBack,
    goForward,
    resetHistory,
    setScroller,
    showView,
    viewState,
    type ArcaTab,
    type HomeTab,
  } from './lib/stores/view'

  interface Props {
    /** 설정 창은 Task 18 이 채운다. */
    onOpenSettings?: () => void
  }
  let { onOpenSettings = () => {} }: Props = $props()

  const FIRST_TAB: Record<Site, string> = { dccon: 'day', arca: 'new' }

  let content: HTMLDivElement | undefined = $state()
  /** 독이 지금 차지하는 높이. 그리드 아래에 이만큼 비워 둔다. */
  let dockPad = $state(0)
  let searchBar: ReturnType<typeof SearchBar> | undefined = $state()

  /** 이후 단축키(Task 18)가 쓴다. */
  export function focusSearch() {
    searchBar?.focus()
  }

  onMount(() => {
    setScroller(
      () => content?.scrollTop ?? 0,
      (y) => {
        if (content) content.scrollTop = y
      },
    )
    // 설정(GIF 움직임 등)을 먼저 읽고 첫 화면을 연다. 못 읽으면 기본값으로 진행한다.
    void (async () => {
      try {
        await loadSettings()
      } catch (e) {
        console.error('설정을 읽지 못했습니다', e)
      }
      await navigate('dccon', 'day')
    })()
    return wireQueueEvents(queue)
  })

  function navigate(site: Site, tab: string) {
    if (site === 'arca') return showView({ kind: 'arca', tab: tab as ArcaTab, page: 1 })
    if (tab === 'all') return showView({ kind: 'all', page: 1 })
    return showView({ kind: 'top', tab: tab as HomeTab })
  }

  function switchSite(site: Site) {
    if (site !== $currentSite) resetHistory()
    void navigate(site, FIRST_TAB[site])
  }

  async function submit(raw: string, type: string) {
    const text = raw.trim()
    if (!text) return
    const site = $currentSite
    try {
      const q = await parseInput(site, text)
      if (q.kind === 'ids') {
        if (q.ids.length === 1) {
          void showView({ kind: 'package', site, id: q.ids[0] })
        } else if (q.ids.length > 1) {
          await enqueue(
            site,
            q.ids.map((id) => ({ id, title: `#${id}`, sorts: null })),
          )
        }
      } else if (q.word) {
        void showView({ kind: 'search', site, word: q.word, type, page: 1 })
      }
    } catch (e) {
      showNotice(isCmdError(e) ? e.message : String(e))
    }
  }

  // 마우스 4번 = 뒤로, 5번 = 앞으로 (button 3, 4). 브라우저와 같다.
  function mouseButton(e: MouseEvent) {
    if (e.button === 3) {
      e.preventDefault()
      if (e.type === 'mouseup') goBack()
    } else if (e.button === 4) {
      e.preventDefault()
      if (e.type === 'mouseup') goForward()
    }
  }

  async function open() {
    try {
      await openFolder()
    } catch (e) {
      showNotice(isCmdError(e) ? e.message : String(e))
    }
  }
</script>

<svelte:window onmousedown={mouseButton} onmouseup={mouseButton} />

<div class="app">
  <Sidebar
    site={$currentSite}
    tab={$activeTab}
    onNavigate={(site, tab) => void navigate(site, tab)}
    onSite={switchSite}
    onHome={() => void navigate($currentSite, FIRST_TAB[$currentSite])}
    onOpenFolder={open}
    {onOpenSettings}
  />
  <main class="main-area">
    <SearchBar bind:this={searchBar} site={$currentSite} onSubmit={submit} />
    <LoadingLine active={$loading} />
    <Heading />
    <div class="stage">
      <div class="content" bind:this={content}>
        {#if $viewState.notice}
          <p class="notice">{$viewState.notice}</p>
        {:else}
          <Grid />
        {/if}
        <div class="dock-pad" style:height="{dockPad}px"></div>
      </div>
      <Glow active={$queue.running && !$queue.cancelling} />
      <Dock bind:pad={dockPad} />
      {#if $notice}
        <div class="toast" role="status">
          <span>{$notice}</span>
          <button type="button" class="close" aria-label="닫기" onclick={dismissNotice}>×</button>
        </div>
      {/if}
    </div>
  </main>
</div>

<style>
  .app {
    display: flex;
    height: 100%;
  }
  .main-area {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    background: var(--bg);
  }
  .stage {
    position: relative;
    flex: 1;
    min-height: 0;
  }
  .content {
    height: 100%;
    overflow-y: auto;
  }
  .dock-pad {
    transition: height 260ms cubic-bezier(0.215, 0.61, 0.355, 1);
  }
  /* 알림은 그리드를 밀지 않고 위에 얹는다. */
  .toast {
    position: absolute;
    top: 0;
    left: 28px;
    right: 28px;
    z-index: 3;
    box-shadow: 0 2px 8px color-mix(in srgb, var(--dock-shadow) 18%, transparent);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 6px 10px;
    border-radius: 6px;
    background: var(--sel-label-bg);
    color: var(--text);
    font-size: 12px;
    white-space: pre-line;
  }
  .close {
    background: transparent;
    padding: 0 6px;
    min-height: 0;
    color: var(--muted);
  }
  .notice {
    margin: 0;
    padding: 32px;
    text-align: center;
    color: var(--muted);
    font-size: 14px;
    white-space: pre-line;
  }
</style>
