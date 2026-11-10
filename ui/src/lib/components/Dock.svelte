<script lang="ts">
  import { dockHidden, queue } from '../stores/queue'
  import ActionBar from './ActionBar.svelte'
  import QueueBar from './QueueBar.svelte'

  /** 지금 독이 차지하는 높이(접히면 손잡이만). 그리드 아래 여백에 쓴다. */
  let { pad = $bindable(0) }: { pad?: number } = $props()

  /** 손잡이만 남았을 때 보이는 높이: 위 여백 8 + 손잡이 20 + 아래 12 (main_window._place_dock). */
  const HANDLE_BLOCK = 40

  let full = $state(0)
  const hidden = $derived($dockHidden)
  const shift = $derived(hidden ? Math.max(0, full - HANDLE_BLOCK) : 0)
  const showQueue = $derived($queue.running || $queue.summary !== null)

  $effect(() => {
    pad = full - shift
  })
</script>

<div class="space" bind:offsetHeight={full} style:transform="translateY({shift}px)">
  <div class="handle-row">
    <button
      type="button"
      class="handle"
      title="다운로드 바 숨기기 / 보이기"
      aria-label="다운로드 바 숨기기 / 보이기"
      aria-expanded={!hidden}
      onclick={() => dockHidden.update((h) => !h)}>{hidden ? '▲' : '▼'}</button
    >
  </div>
  <div class="dock" inert={hidden}>
    {#if showQueue}
      <QueueBar />
    {:else}
      <ActionBar />
    {/if}
  </div>
</div>

<style>
  .space {
    --sh1: 8%;
    --sh2: 10%;
    --sh3: 12%;
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    padding: 8px 28px 16px;
    pointer-events: none;
    transition: transform 260ms cubic-bezier(0.215, 0.61, 0.355, 1);
  }
  .handle-row,
  .dock {
    max-width: 620px;
    margin: 0 auto;
  }
  .dock {
    pointer-events: auto;
  }
  .handle-row {
    display: flex;
    justify-content: center;
    margin-bottom: 4px;
  }
  .handle {
    pointer-events: auto;
    width: 44px;
    height: 20px;
    padding: 2px 0;
    min-height: 0;
    border: 1px solid var(--dock-border);
    border-radius: 6px;
    background: var(--btn-bg);
    color: var(--muted);
    font-size: 9px;
  }
  .handle:hover,
  .handle:focus-visible {
    border-color: var(--focus);
    color: var(--text);
    outline: none;
  }
  .dock {
    background: var(--card-bg);
    border: 1px solid var(--dock-border);
    border-radius: 12px;
    /* 블러 이펙트 없이 겹쳐 그린 옅은 그림자 (DockShade). */
    box-shadow:
      0 3px 10px 3px color-mix(in srgb, var(--dock-shadow) var(--sh3), transparent),
      0 2px 14px 6px color-mix(in srgb, var(--dock-shadow) var(--sh2), transparent),
      0 4px 20px 10px color-mix(in srgb, var(--dock-shadow) var(--sh1), transparent);
    overflow: hidden;
  }
  :global(:root[data-theme='dark']) .space {
    --sh1: 18%;
    --sh2: 22%;
    --sh3: 26%;
  }
  @media (prefers-color-scheme: dark) {
    :global(:root:not([data-theme])) .space {
      --sh1: 18%;
      --sh2: 22%;
      --sh3: 26%;
    }
  }
</style>
