<script lang="ts">
  import { onMount } from 'svelte'
  import {
    applyUpdate,
    cancelUpdate,
    downloadUpdate,
    isCmdError,
    onEvent,
    openReleasePage,
    skipVersion,
    type ReleaseInfo,
    type UpdateProgress,
  } from '../api'
  import { showNotice } from '../stores/notice'
  import { queue } from '../stores/queue'
  import Modal from './Modal.svelte'

  let {
    release,
    version,
    offerSkip = false,
    beforeApply,
    onClose,
  }: {
    release: ReleaseInfo
    version: string
    offerSkip?: boolean
    /** 앱이 꺼지기 전에 할 일(설정 저장 등). */
    beforeApply?: () => Promise<void>
    onClose: () => void
  } = $props()

  type Phase = 'idle' | 'downloading' | 'error' | 'confirm'
  let phase = $state<Phase>('idle')
  let progress = $state<UpdateProgress | null>(null)
  let errorText = $state('')
  /** 닫혔는데 늦게 도착한 결과를 무시하려는 표시. */
  let closed = false

  const MB = 1048576
  const mb = (n: number) =>
    (n / MB).toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
  const status = $derived.by(() => {
    if (!release.can_apply)
      return '이 실행 방식에서는 자동 업데이트를 할 수 없습니다. 릴리즈 페이지에서 받아주세요.'
    if (phase === 'error') return `업데이트를 받지 못했습니다.\n${errorText}`
    if (phase === 'downloading') {
      const name = release.asset_name ?? ''
      return progress && progress.total > 0
        ? `${name}  ${mb(progress.done)} / ${mb(progress.total)} MB`
        : `${name} 받는 중…`
    }
    return ''
  })
  const percent = $derived(
    progress && progress.total > 0 ? Math.min(100, (progress.done * 100) / progress.total) : null,
  )

  onMount(() => {
    let off: (() => void) | undefined
    void onEvent<UpdateProgress>('update-progress', (p) => (progress = p)).then((u) => {
      if (closed) u()
      else off = u
    })
    return () => {
      closed = true
      off?.()
    }
  })

  function fail(e: unknown): string {
    return isCmdError(e) ? e.message : String(e)
  }

  function close() {
    // 받는 도중에 닫으면 받기를 멈춘다.
    if (phase === 'downloading') void cancelUpdate().catch(() => undefined)
    onClose()
  }

  async function openPage() {
    try {
      await openReleasePage()
    } catch (e) {
      showNotice(fail(e))
    }
  }

  async function start() {
    if (!release.can_apply) {
      await openPage()
      onClose()
      return
    }
    phase = 'downloading'
    progress = null
    try {
      await downloadUpdate()
    } catch (e) {
      if (closed) return
      errorText = fail(e)
      phase = 'error'
      return
    }
    if (closed) return
    // 받던 중에 큰 작업이 돌고 있으면 한 번 묻는다 (main_window._apply_update).
    if ($queue.running) phase = 'confirm'
    else await apply()
  }

  async function apply() {
    try {
      try {
        await beforeApply?.()
      } catch {
        // 설정을 못 저장해도 업데이트는 계속한다.
      }
      await applyUpdate()
      // 성공하면 앱이 종료된다.
    } catch (e) {
      if (closed) return
      showNotice(isCmdError(e) && e.kind === 'update' ? `업데이트를 시작하지 못했습니다.
${fail(e)}` : fail(e))
      // 교체에 실패하면 손으로 받을 수 있게 릴리즈 페이지를 연다. 이미 적용된 뒤라면 열지 않는다.
      if (!(isCmdError(e) && e.kind === 'restart')) await openPage()
      onClose()
    }
  }

  async function skip() {
    try {
      await skipVersion(release.version)
    } catch (e) {
      showNotice(fail(e))
    }
    onClose()
  }
</script>

<Modal title="업데이트" onClose={close} width={520}>
  {#if phase === 'confirm'}
    <h2 class="crumb">업데이트</h2>
    <!-- 소스 줄바꿈이 pre-line 으로 그대로 보이지 않도록 한 문자열로 둔다. -->
    <p class="msg">{'다운로드가 진행 중입니다. 중단하고 다시 시작할까요?\n받다 만 패키지는 다음에 다시 받으면 빠진 것만 채워집니다.'}</p>
    <div class="buttons">
      <button type="button" onclick={onClose}>아니요</button>
      <button type="button" class="primary" data-autofocus onclick={apply}>예</button>
    </div>
  {:else}
    <h2 class="crumb">새 버전 {release.version}</h2>
    <p class="sub">지금 쓰는 버전은 {version} 입니다.</p>

    <!-- svelte-ignore a11y_no_noninteractive_tabindex (키보드로 스크롤하려면 포커스가 필요하다) -->
    <div class="notes" tabindex="0" role="region" aria-label="변경 내역">
      {release.notes.trim() || '변경 내역이 없습니다.'}
    </div>

    {#if phase === 'downloading'}
      <div
        class="track"
        role="progressbar"
        aria-label="업데이트 받는 중"
        aria-valuemin="0"
        aria-valuemax="100"
        aria-valuenow={percent === null ? undefined : Math.round(percent)}
      >
        <div class="chunk" class:indeterminate={percent === null} style:width="{percent ?? 30}%"></div>
      </div>
    {/if}
    {#if status}
      <p class="status">{status}</p>
    {/if}

    <div class="buttons">
      {#if offerSkip && phase !== 'downloading'}
        <button type="button" onclick={skip}>이 버전 건너뛰기</button>
      {/if}
      <span class="spacer"></span>
      <button type="button" onclick={close}>
        {phase === 'downloading' ? '취소' : phase === 'error' ? '닫기' : '나중에'}
      </button>
      <!-- 처음 포커스를 받아 Enter 가 기본 동작이 된다 (파이썬판 setDefault) -->
      <button
        type="button"
        class="primary"
        data-autofocus
        disabled={phase === 'downloading'}
        onclick={start}
      >
        {phase === 'error' ? '다시 시도' : release.can_apply ? '지금 업데이트' : '릴리즈 페이지 열기'}
      </button>
    </div>
  {/if}
</Modal>

<style>
  /* update_dialog.py: 제목은 #crumb (22px), 줄 사이 14, 변경 내역은 QTextBrowser 스타일 */
  .crumb {
    margin: 0 0 14px;
    font-size: 22px;
    font-weight: 600;
    line-height: 29px;
    color: var(--heading);
  }
  .sub {
    margin: 0 0 14px;
    color: var(--muted);
    font-size: 12px;
  }
  .notes {
    height: 220px;
    overflow-y: auto;
    padding: 8px;
    border: 1px solid var(--btn-border);
    border-radius: 8px;
    background: var(--tree-bg);
    font-size: 13px;
    line-height: 1.5;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    user-select: text;
  }
  .track {
    height: 6px;
    margin-top: 14px;
    border-radius: 3px;
    background: var(--dl-track);
    overflow: hidden;
  }
  .chunk {
    height: 100%;
    border-radius: 3px;
    background: var(--accent);
    transition: width 200ms linear;
  }
  .chunk.indeterminate {
    animation: slide 1.1s ease-in-out infinite alternate;
  }
  @keyframes slide {
    from {
      margin-left: 0;
    }
    to {
      margin-left: 70%;
    }
  }
  :global(:root[data-reduce-motion]) .chunk.indeterminate {
    animation: none;
  }
  .status {
    margin: 10px 0 0;
    color: var(--muted);
    font-size: 12px;
    white-space: pre-line;
  }
  .msg {
    margin: 0;
    white-space: pre-line;
  }
  .buttons {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 16px;
  }
  .spacer {
    flex: 1;
  }
</style>
