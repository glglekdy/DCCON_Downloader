<script lang="ts">
  import { goPage, stepPage, viewState } from '../stores/view'
  import PageJump from './PageJump.svelte'

  let jumping = $state(false)
  const s = $derived($viewState)
</script>

<header class="heading">
  <div class="row">
    <h1 class="crumb">{s.crumb}</h1>
    {#if s.resultText}
      <span class="result">{s.resultText}</span>
    {/if}
    <span class="spacer"></span>
    {#if s.paged}
      <button
        type="button"
        class="ghost step"
        title="이전 페이지"
        aria-label="이전 페이지"
        disabled={s.page <= 1}
        onclick={() => stepPage(-1)}>‹</button
      >
      <button
        type="button"
        class="ghost"
        title="눌러서 원하는 페이지로 이동"
        onclick={() => s.pages > 1 && (jumping = true)}>{s.page} / {s.pages}</button
      >
      <button
        type="button"
        class="ghost step"
        title="다음 페이지"
        aria-label="다음 페이지"
        disabled={s.page >= s.pages}
        onclick={() => stepPage(1)}>›</button
      >
    {/if}
  </div>
  {#if s.hint}
    <div class="hint">{s.hint}</div>
  {/if}
</header>

{#if jumping}
  <PageJump page={s.page} pages={s.pages} onJump={goPage} onClose={() => (jumping = false)} />
{/if}

<style>
  .heading {
    padding: 18px 28px 12px;
    background: var(--bg);
  }
  .row {
    display: flex;
    align-items: flex-end;
    gap: 10px;
  }
  .crumb {
    margin: 0;
    font-size: 22px;
    font-weight: 600;
    color: var(--heading);
    line-height: 1.3;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
  }
  .result {
    color: var(--muted);
    font-size: 12px;
    padding-bottom: 3px;
    white-space: nowrap;
  }
  .spacer {
    flex: 1;
  }
  .ghost {
    background: transparent;
    color: var(--muted);
  }
  .ghost:hover {
    background: var(--btn-hover-bg);
    color: var(--text);
  }
  .ghost:disabled {
    background: transparent;
    color: var(--disabled-fg);
  }
  .step {
    width: 32px;
    padding: 6px 0;
  }
  .hint {
    margin-top: 4px;
    color: var(--muted);
    font-size: 12px;
  }
</style>
