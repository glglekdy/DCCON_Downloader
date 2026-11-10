<script lang="ts">
  import { onDestroy, onMount, type Snippet } from 'svelte'
  import { get } from 'svelte/store'
  import { modalStack, popModal, pushModal } from '../stores/modal'

  let {
    title,
    onClose,
    width = 520,
    children,
  }: { title: string; onClose: () => void; width?: number; children: Snippet } = $props()

  let box: HTMLDivElement | undefined = $state()
  let id = 0
  let opener: Element | null = null

  const FOCUSABLE =
    'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

  function focusables(): HTMLElement[] {
    return box ? [...box.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((e) => !e.closest('[inert]')) : []
  }

  onMount(() => {
    opener = document.activeElement
    id = pushModal()
    // 처음 포커스는 안쪽 첫 입력(없으면 상자 자체)에.
    ;(focusables()[0] ?? box)?.focus()
  })

  onDestroy(() => {
    if (id) popModal(id)
    // 닫은 뒤 열었던 곳으로 포커스를 돌려준다.
    if (opener instanceof HTMLElement && opener.isConnected) opener.focus()
  })

  function keydown(e: KeyboardEvent) {
    // 겹친 창이면 맨 위만 반응한다.
    if (get(modalStack).at(-1) !== id) return
    if (e.key === 'Escape') {
      e.preventDefault()
      e.stopPropagation()
      onClose()
    } else if (e.key === 'Tab' && box) {
      const list = focusables()
      if (list.length === 0) {
        e.preventDefault()
        box.focus()
        return
      }
      const first = list[0]
      const last = list[list.length - 1]
      const active = document.activeElement
      if (e.shiftKey && (active === first || active === box || !box.contains(active))) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && (active === last || !box.contains(active))) {
        e.preventDefault()
        first.focus()
      }
    }
  }
</script>

<svelte:window onkeydown={keydown} />

<div class="backdrop" role="presentation">
  <div
    class="modal"
    role="dialog"
    aria-modal="true"
    aria-label={title}
    tabindex="-1"
    bind:this={box}
    style:width="min({width}px, calc(100vw - 32px))"
  >
    {@render children()}
  </div>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 20;
    display: flex;
    align-items: center;
    justify-content: center;
    background: color-mix(in srgb, var(--dock-shadow) 40%, transparent);
  }
  .modal {
    max-height: calc(100vh - 32px);
    overflow-y: auto;
    box-sizing: border-box;
    padding: 24px 28px;
    border: 1px solid var(--dock-border);
    border-radius: 12px;
    background: var(--surface);
    color: var(--text);
    box-shadow: 0 8px 28px color-mix(in srgb, var(--dock-shadow) 28%, transparent);
    outline: none;
  }
</style>
