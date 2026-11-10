<script lang="ts">
  import { onMount } from 'svelte'
  import { enqueue, isCmdError, openFolder, parseInput, type Site } from './lib/api'
  import Grid from './lib/components/Grid.svelte'
  import Heading from './lib/components/Heading.svelte'
  import LoadingLine from './lib/components/LoadingLine.svelte'
  import SearchBar from './lib/components/SearchBar.svelte'
  import Sidebar from './lib/components/Sidebar.svelte'
  import { activeTab, currentSite, loading } from './lib/stores/nav'
  import { loadSettings } from './lib/stores/settings'
  import {
    goBack,
    goForward,
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
    loadSettings().catch((e) => console.error('설정을 읽지 못했습니다', e))
    void navigate('dccon', 'day')
  })

  function navigate(site: Site, tab: string) {
    if (site === 'arca') return showView({ kind: 'arca', tab: tab as ArcaTab, page: 1 })
    if (tab === 'all') return showView({ kind: 'all', page: 1 })
    return showView({ kind: 'top', tab: tab as HomeTab })
  }

  function switchSite(site: Site) {
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
      console.error(isCmdError(e) ? e.message : e)
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
      console.error(isCmdError(e) ? e.message : e)
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
    <div class="content" bind:this={content}>
      {#if $viewState.notice}
        <p class="notice">{$viewState.notice}</p>
      {:else}
        <Grid />
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
  .content {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
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
