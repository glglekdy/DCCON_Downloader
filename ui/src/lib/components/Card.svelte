<script lang="ts">
  import type { Snippet } from 'svelte'
  import check from '../../assets/check.svg'

  interface Props {
    title: string
    subtitle?: string
    selected: boolean
    tooltip?: string
    checkTooltip?: string
    onToggle?: () => void
    onOpen?: () => void
    children: Snippet
  }
  let {
    title,
    subtitle = '',
    selected,
    tooltip,
    checkTooltip,
    onToggle = () => {},
    onOpen,
    children,
  }: Props = $props()

  function keydown(e: KeyboardEvent) {
    if (e.key === ' ') {
      e.preventDefault()
      onToggle()
    } else if (e.key === 'Enter' && onOpen) {
      e.preventDefault()
      onOpen()
    }
  }
</script>

<!-- 클릭은 선택 토글, 더블클릭은 열기. 더블클릭에는 클릭이 두 번 앞서므로 토글이 제자리로 돌아온다. -->
<div
  class="card"
  class:selected
  role="checkbox"
  aria-checked={selected}
  aria-label={`${title} 선택`}
  tabindex="0"
  title={tooltip ?? title}
  onclick={() => onToggle()}
  ondblclick={() => onOpen?.()}
  onkeydown={keydown}
>
  <div class="preview">
    {@render children()}
    <span class="ring"></span>
  </div>
  <span
    class="check"
    class:on={selected}
    title={checkTooltip}
    style:--check-icon={`url("${check}")`}
  ></span>
  <div class="label">{title}</div>
  <div class="sub">{subtitle}</div>
</div>

<style>
  .card {
    position: relative;
    width: 156px;
    box-sizing: border-box;
    padding: 6px 6px 8px;
    border-radius: 8px;
    background: transparent;
    cursor: pointer;
    transition: background 120ms;
    outline: none;
  }
  .card:hover,
  .card.selected {
    background: var(--card-bg);
  }
  .card:focus-visible {
    outline: 2px solid var(--focus);
  }
  .preview {
    position: relative;
    width: 144px;
    height: 144px;
  }
  /* 선택하면 썸네일 바깥 2px 에 강조색 테두리 */
  .ring {
    position: absolute;
    inset: -2px;
    border: 2px solid var(--accent);
    border-radius: 8px;
    opacity: 0;
    transition: opacity 160ms;
    pointer-events: none;
  }
  .selected .ring {
    opacity: 1;
  }
  /* 1.3.0 에서 실측한 자리와 크기: 카드 기준 (12, 18), 16px + 테두리 1px. */
  .check {
    position: absolute;
    left: 12px;
    top: 18px;
    width: 18px;
    height: 18px;
    box-sizing: border-box;
    border-radius: 4px;
    background: var(--check-bg);
    border: 1px solid var(--check-border);
    opacity: 0;
  }
  .card:hover .check,
  .check.on {
    opacity: 1;
  }
  .check:hover {
    border-color: var(--focus);
  }
  .check.on {
    background: var(--accent) var(--check-icon) center / 16px 16px no-repeat;
    border-color: var(--accent);
  }
  .label,
  .sub {
    width: 144px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .label {
    margin-top: 8px;
    color: var(--text);
    font-size: 13px;
    font-weight: 500;
  }
  .sub {
    margin-top: 2px;
    min-height: 1.3em;
    color: var(--card-subtitle);
    font-size: 11px;
  }
</style>
