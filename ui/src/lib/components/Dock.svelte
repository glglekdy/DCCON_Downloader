<script lang="ts">
  import { dockHidden, queue } from '../stores/queue'
  import ActionBar from './ActionBar.svelte'
  import QueueBar from './QueueBar.svelte'

  /** 지금 독이 차지하는 높이(접히면 손잡이만). 그리드 아래 여백에 쓴다. */
  let { pad = $bindable(0) }: { pad?: number } = $props()

  /** 손잡이만 남았을 때 보이는 높이: 위 여백 8 + 손잡이 20 + 아래 12 (main_window._place_dock). */
  const HANDLE_BLOCK = 40

  /** glow.DockShade: 독 둘레를 (퍼짐, 알파/255) 만큼 넓힌 둥근 사각형 세 장을 겹쳐 칠한다. */
  const SHADES: [number, number][] = [
    [10, 8],
    [6, 10],
    [3, 12],
  ]

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
  <div class="dock-wrap">
    {#each SHADES as [spread, alpha] (spread)}
      <span
        class="shade"
        style:inset="{-spread * 0.4}px {-spread}px {-(spread + 2)}px {-spread}px"
        style:border-radius="{12 + spread}px"
        style:--alpha={alpha}
      ></span>
    {/each}
    <div class="dock" inert={hidden}>
      {#if showQueue}
        <QueueBar />
      {:else}
        <ActionBar />
      {/if}
    </div>
  </div>
</div>

<style>
  .space {
    /* 어두운 테마에서는 그림자를 2.2배 진하게 (DockShade.paintEvent). */
    --boost: 1;
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    padding: 8px 28px 16px;
    pointer-events: none;
    transition: transform 260ms cubic-bezier(0.215, 0.61, 0.355, 1);
  }
  .handle-row,
  .dock-wrap {
    max-width: 620px;
    margin: 0 auto;
  }
  .dock-wrap {
    position: relative;
  }
  .handle-row {
    display: flex;
    justify-content: center;
    /* 손잡이 줄 아래 여백 6 + 레이아웃 간격 6 (main_window: handle_row, dock_margin) */
    margin-bottom: 12px;
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
  /* #dockToggle:focus - 누른 뒤에도 초점 테두리가 남는다 (1.3.0) */
  .handle:focus {
    border-color: var(--focus);
    color: var(--text);
    outline: none;
  }
  .shade {
    position: absolute;
    background: color-mix(
      in srgb,
      var(--dock-shadow) calc(min(255, var(--alpha) * var(--boost)) / 255 * 100%),
      transparent
    );
  }
  .dock {
    position: relative;
    pointer-events: auto;
    background: var(--card-bg);
    border: 1px solid var(--dock-border);
    border-radius: 12px;
    /* 테두리 안쪽 레이아웃 여백 1px (dock_layout.setContentsMargins(1, 1, 1, 1)) */
    padding: 1px;
    overflow: hidden;
  }
  :global(:root[data-theme='dark']) .space {
    --boost: 2.2;
  }
  @media (prefers-color-scheme: dark) {
    :global(:root:not([data-theme])) .space {
      --boost: 2.2;
    }
  }
</style>
