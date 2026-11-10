<script lang="ts">
  import { getVersion } from '@tauri-apps/api/app'
  import { onMount } from 'svelte'
  import {
    arcaForgetSession,
    arcaLogin,
    arcaLoginCancel,
    arcaStatus,
    checkUpdate,
    enqueue,
    isCmdError,
    onEvent,
    openFolder,
    parseInput,
    takeLastError,
    type LoginFinished,
    type ReleaseInfo,
    type Site,
  } from './lib/api'
  import Dock from './lib/components/Dock.svelte'
  import Glow from './lib/components/Glow.svelte'
  import Grid from './lib/components/Grid.svelte'
  import Heading from './lib/components/Heading.svelte'
  import LoadingLine from './lib/components/LoadingLine.svelte'
  import LoginPrompt, { type LoginPhase } from './lib/components/LoginPrompt.svelte'
  import SearchBar from './lib/components/SearchBar.svelte'
  import SettingsDialog from './lib/components/SettingsDialog.svelte'
  import Sidebar from './lib/components/Sidebar.svelte'
  import UpdateDialog from './lib/components/UpdateDialog.svelte'
  import { isFocusSearch } from './lib/shortcuts'
  import { modalStack } from './lib/stores/modal'
  import { activeTab, currentSite, loading } from './lib/stores/nav'
  import { dismissNotice, notice, showNotice } from './lib/stores/notice'
  import { queue } from './lib/stores/queue'
  import { wireQueueEvents } from './lib/stores/queue-events'
  import { loadSettings, settings } from './lib/stores/settings'
  import {
    goBack,
    goForward,
    loginNeeded,
    resetHistory,
    setScroller,
    showView,
    viewState,
    type ArcaTab,
    type HomeTab,
  } from './lib/stores/view'

  const FIRST_TAB: Record<Site, string> = { dccon: 'day', arca: 'new' }

  let content: HTMLDivElement | undefined = $state()
  /** 독이 지금 차지하는 높이. 그리드 아래에 이만큼 비워 둔다. */
  let dockPad = $state(0)
  let searchBar: ReturnType<typeof SearchBar> | undefined = $state()

  let settingsOpen = $state(false)
  /** 시작할 때 확인에서 찾은 새 버전. */
  let startupRelease = $state<ReleaseInfo | null>(null)
  let version = $state('')
  /** 아카콘 로그인 창 단계. null 이면 닫혀 있다. */
  let loginPhase = $state<LoginPhase | null>(null)
  let loginMessage = $state('')
  /** 지금 기다리는 로그인 시도 번호. 다른 번호의 결과는 무시한다. */
  let loginId: number | null = null
  /** startLogin 을 부른 차례. 늦게 돌아온 arcaLogin() 을 가려낸다. */
  let loginSeq = 0
  /** arcaLogin() 이 번호를 돌려주기 전에 도착한 결과. */
  const earlyResults = new Map<number, LoginFinished>()

  export function focusSearch() {
    searchBar?.focus()
  }

  function onOpenSettings() {
    // 설정을 아직 못 읽었으면 열지 않는다 (기본값을 저장해 덮어쓰지 않도록).
    if ($settings) settingsOpen = true
  }

  /** 시작하고 조금 뒤 새 버전을 조용히 확인한다 (main_window._startup_update_check). */
  async function startupCheck() {
    try {
      const failure = await takeLastError()
      if (failure) showNotice(failure, 10000)
    } catch {
      // 못 읽어도 업데이트 확인은 계속한다.
    }
    try {
      const r = await checkUpdate(false)
      if (r) {
        version = await getVersion().catch(() => '')
        startupRelease = r
      }
    } catch {
      // 시작할 때 확인은 실패해도 알리지 않는다. 오프라인일 수도 있다.
    }
  }

  function keydown(e: KeyboardEvent) {
    if (isFocusSearch(e)) {
      e.preventDefault()
      // 모달이 떠 있으면 뒤의 입력창으로 포커스가 새지 않게 한다.
      if ($modalStack.length === 0) focusSearch()
    }
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
      setTimeout(() => void startupCheck(), 1500)
    })()
    // 목록이 login_required 로 실패하면 저장한 세션을 버리고 다시 로그인시킨다 (main_window._on_nav_error).
    const offNeeded = loginNeeded.subscribe((needed) => {
      if (!needed) return
      loginNeeded.set(false)
      if (loginPhase === 'waiting') return
      // 세션 파일과 클라이언트 쿠키만 버린다. 로그인 창의 쿠키는 남겨 다시 로그인이 빨라지게 한다.
      void arcaForgetSession()
        .catch(() => undefined)
        .finally(requireLogin)
    })
    let closed = false
    let offLogin: (() => void) | undefined
    void onEvent<LoginFinished>('login-finished', onLoginFinished).then((u) => {
      if (closed) u()
      else offLogin = u
    })
    const offQueue = wireQueueEvents(queue)
    return () => {
      closed = true
      offLogin?.()
      offNeeded()
      offQueue()
    }
  })

  function navigate(site: Site, tab: string) {
    if (site === 'arca') return showView({ kind: 'arca', tab: tab as ArcaTab, page: 1 })
    if (tab === 'all') return showView({ kind: 'all', page: 1 })
    return showView({ kind: 'top', tab: tab as HomeTab })
  }

  async function switchSite(site: Site) {
    // 세션이 없으면 로그인부터 묻는다. 세그먼트는 지금 사이트에 남는다 (main_window._switch_site).
    if (site === 'arca' && !(await arcaStatus().catch(() => false))) {
      requireLogin()
      return
    }
    if (site !== $currentSite) resetHistory()
    void navigate(site, FIRST_TAB[site])
  }

  // ------------------------------------------------- 아카콘 로그인 (main_window._require_login)
  function requireLogin() {
    if (loginPhase === 'waiting') return
    loginMessage = ''
    loginPhase = 'ask'
  }

  /** 아카콘을 보고 있었으면 디시콘으로 돌아간다. */
  function leaveArca() {
    if ($currentSite !== 'arca') return
    resetHistory()
    void navigate('dccon', FIRST_TAB.dccon)
  }

  async function startLogin() {
    const mine = ++loginSeq
    loginPhase = 'waiting'
    loginId = null
    earlyResults.clear()
    let id: number
    try {
      id = await arcaLogin()
    } catch (e) {
      if (mine !== loginSeq || loginPhase !== 'waiting') return
      loginMessage = isCmdError(e) ? e.message : String(e)
      loginPhase = 'failed'
      return
    }
    // 그 사이 취소했거나 새로 시작했으면 이 시도의 결과는 받지 않는다.
    if (mine !== loginSeq) return
    if (loginPhase !== 'waiting') {
      // 취소가 창이 만들어지기 전에 도착했으면 그 창은 아직 열려 있다. 지금 닫는다.
      void arcaLoginCancel().catch(() => undefined)
      return
    }
    loginId = id
    const early = earlyResults.get(id)
    earlyResults.clear()
    if (early) onLoginFinished(early)
  }

  /** 묻기 취소, 기다리기 취소, 실패 확인. 취소한 시도의 결과는 오더라도 무시한다. */
  function closeLogin() {
    const phase = loginPhase
    loginPhase = null
    loginId = null
    if (phase === 'waiting') void arcaLoginCancel().catch(() => undefined)
    leaveArca()
  }

  function onLoginFinished(r: LoginFinished) {
    if (loginPhase !== 'waiting') return
    if (loginId === null) {
      // 번호를 받기 전이면 잠시 맡아 둔다.
      earlyResults.set(r.id, r)
      return
    }
    if (r.id !== loginId) return
    loginId = null
    if (r.ok) {
      loginPhase = null
      if (r.message) showNotice(r.message, 10000)
      if ($currentSite !== 'arca') resetHistory()
      void navigate('arca', FIRST_TAB.arca)
    } else {
      loginMessage = r.message
      loginPhase = 'failed'
    }
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
    // 모달이 떠 있으면 뒤 화면은 움직이지 않는다.
    if ($modalStack.length > 0) return
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

<svelte:window onmousedown={mouseButton} onmouseup={mouseButton} onkeydown={keydown} />

<div class="app">
  <Sidebar
    site={$currentSite}
    tab={$activeTab}
    onNavigate={(site, tab) => void navigate(site, tab)}
    onSite={(site) => void switchSite(site)}
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

{#if settingsOpen && $settings}
  <SettingsDialog initial={$settings} onClose={() => (settingsOpen = false)} />
{/if}
{#if loginPhase}
  <LoginPrompt phase={loginPhase} message={loginMessage} onOk={startLogin} onCancel={closeLogin} />
{/if}
{#if startupRelease}
  <UpdateDialog
    release={startupRelease}
    {version}
    offerSkip={true}
    onClose={() => (startupRelease = null)}
  />
{/if}

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
