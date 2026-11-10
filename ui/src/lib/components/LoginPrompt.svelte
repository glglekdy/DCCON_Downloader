<script lang="ts" module>
  /** ask: 로그인할지 묻는다. waiting: 로그인 창이 떠 있다. failed: 로그인하지 못했다. */
  export type LoginPhase = 'ask' | 'waiting' | 'failed'
</script>

<script lang="ts">
  import Modal from './Modal.svelte'

  let {
    phase,
    message = '',
    onOk,
    onCancel,
  }: {
    phase: LoginPhase
    /** failed 일 때 보일 사유. */
    message?: string
    /** ask 에서 확인. */
    onOk: () => void
    /** ask·waiting 에서 취소, failed 에서 확인, Esc. */
    onCancel: () => void
  } = $props()

  const ASK =
    '아카콘을 보려면 아카라이브 로그인이 필요합니다.\n\n' +
    '확인을 누르면 로그인 창이 열립니다.\n' +
    '로그인을 마치면 아카콘 화면으로 넘어갑니다.'
  const WAITING =
    '열린 창에서 아카라이브에 로그인해 주세요…\n' +
    '로그인을 마쳤는데 넘어가지 않으면 로그인 창을 닫아 주세요.'
</script>

<!-- main_window._require_login 의 알림창·진행창·경고창 -->
<Modal title="아카콘 로그인" onClose={onCancel} width={440}>
  <h2 class="crumb">아카콘 로그인</h2>
  {#if phase === 'ask'}
    <!-- 소스 줄바꿈이 pre-line 으로 그대로 보이지 않도록 문구는 한 문자열로 둔다. -->
    <p class="msg">{ASK}</p>
    <!-- QMessageBox: 확인, 취소 -->
    <div class="buttons">
      <button type="button" data-autofocus onclick={onOk}>확인</button>
      <button type="button" onclick={onCancel}>취소</button>
    </div>
  {:else if phase === 'waiting'}
    <p class="msg">{WAITING}</p>
    <div class="track" role="progressbar" aria-label="로그인 기다리는 중">
      <div class="chunk"></div>
    </div>
    <div class="buttons">
      <button type="button" data-autofocus onclick={onCancel}>취소</button>
    </div>
  {:else}
    <p class="msg">로그인하지 못했습니다.{'\n'}{message}</p>
    <div class="buttons">
      <button type="button" class="primary" data-autofocus onclick={onCancel}>확인</button>
    </div>
  {/if}
</Modal>

<style>
  .crumb {
    margin: 0 0 10px;
    font-size: 16px;
    font-weight: 600;
    color: var(--heading);
  }
  .msg {
    margin: 0;
    white-space: pre-line;
    line-height: 1.5;
  }
  .track {
    height: 6px;
    margin-top: 14px;
    border-radius: 3px;
    background: var(--dl-track);
    overflow: hidden;
  }
  .chunk {
    width: 30%;
    height: 100%;
    border-radius: 3px;
    background: var(--accent);
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
  :global(:root[data-reduce-motion]) .chunk {
    animation: none;
  }
  .buttons {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 16px;
  }
</style>
