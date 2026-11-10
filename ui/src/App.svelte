<script lang="ts">
  import { onMount } from 'svelte'
  import { isCmdError, openFolder, type Site } from './lib/api'
  import LoadingLine from './lib/components/LoadingLine.svelte'
  import SearchBar from './lib/components/SearchBar.svelte'
  import Sidebar from './lib/components/Sidebar.svelte'
  import { activeTab, currentSite, loading } from './lib/stores/nav'
  import { loadSettings } from './lib/stores/settings'

  interface Props {
    /** 화면 이동은 Task 16 이 채운다. */
    onNavigate?: (site: Site, tab: string) => void
    /** 설정 창은 Task 18 이 채운다. */
    onOpenSettings?: () => void
  }
  let { onNavigate = () => {}, onOpenSettings = () => {} }: Props = $props()

  const FIRST_TAB: Record<Site, string> = { dccon: 'day', arca: 'new' }

  onMount(() => {
    loadSettings().catch((e) => console.error('설정을 읽지 못했습니다', e))
  })

  function navigate(site: Site, tab: string) {
    currentSite.set(site)
    activeTab.set(tab)
    onNavigate(site, tab)
  }

  function switchSite(site: Site) {
    navigate(site, FIRST_TAB[site])
  }

  async function open() {
    try {
      await openFolder()
    } catch (e) {
      console.error(isCmdError(e) ? e.message : e)
    }
  }
</script>

<div class="app">
  <Sidebar
    site={$currentSite}
    tab={$activeTab}
    onNavigate={navigate}
    onSite={switchSite}
    onHome={() => navigate($currentSite, FIRST_TAB[$currentSite])}
    onOpenFolder={open}
    {onOpenSettings}
  />
  <main class="main-area">
    <SearchBar site={$currentSite} />
    <LoadingLine active={$loading} />
    <div class="content"></div>
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
  }
</style>
