<script lang="ts">
  import { onDestroy, onMount, tick } from 'svelte'
  import { get } from 'svelte/store'
  import { modalStack } from '../stores/modal'

  interface Props {
    page: number
    pages: number
    onJump: (page: number) => void
    onClose: () => void
  }
  let { page, pages, onJump, onClose }: Props = $props()

  // svelte-ignore state_referenced_locally
  let value = $state<number | null>(page)
  const opener = document.activeElement as HTMLElement | null
  let input: HTMLInputElement | undefined = $state()

  onMount(async () => {
    await tick()
    input?.focus()
    input?.select()
  })

  onDestroy(() => opener?.focus?.())

  function submit(e: Event) {
    e.preventDefault()
    if (value === null || value === undefined || !Number.isFinite(Number(value))) return
    onJump(Math.max(1, Math.min(pages, Math.round(Number(value)))))
    onClose()
  }
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && get(modalStack).length === 0 && onClose()} />

<div class="backdrop" role="presentation" onmousedown={onClose}>
  <div
    class="dialog"
    role="dialog"
    tabindex="-1"
    aria-modal="true"
    aria-label="페이지 이동"
    onmousedown={(e) => e.stopPropagation()}
  >
  <form onsubmit={submit}>
    <div class="title">페이지 이동</div>
    <label>
      이동할 페이지 (1 ~ {pages.toLocaleString('en-US')})
      <input bind:this={input} type="number" min="1" max={pages} bind:value />
    </label>
    <div class="buttons">
      <button type="button" onclick={onClose}>취소</button>
      <button type="submit" class="primary">확인</button>
    </div>
  </form>
  </div>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 50;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0.35);
  }
  .dialog {
    display: flex;
    flex-direction: column;
    gap: 12px;
    min-width: 280px;
    padding: 18px 20px;
    border-radius: 10px;
    background: var(--popup-bg);
    border: 1px solid var(--topbar-border);
    color: var(--text);
    user-select: text;
  }
  form {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .title {
    font-size: 15px;
    font-weight: 600;
    color: var(--heading);
  }
  label {
    display: flex;
    flex-direction: column;
    gap: 6px;
    color: var(--muted);
  }
  .buttons {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }
</style>
