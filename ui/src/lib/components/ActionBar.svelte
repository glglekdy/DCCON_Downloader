<script lang="ts">
  import { enqueue, isCmdError } from '../api'
  import { showNotice } from '../stores/notice'
  import { jobsFor } from '../stores/queue'
  import { selection, viewState } from '../stores/view'

  const sel = $derived($selection)
  const s = $derived($viewState)
  const noun = $derived(s.pkg ? '개' : '개 패키지')

  function selectAll() {
    selection.setAll(s.pkg ? s.pkg.items.map((i) => i.sort) : s.rows.map((b) => b.idx), true)
  }

  /** enqueue 가 돌아오기 전에 다시 누르면 같은 작업이 두 번 들어간다. */
  let busy = $state(false)

  async function download() {
    const jobs = jobsFor(s, sel)
    if (!jobs.length || busy) return
    busy = true
    try {
      await enqueue(s.site, jobs)
      selection.clear()
    } catch (e) {
      showNotice(isCmdError(e) ? e.message : String(e))
    } finally {
      busy = false
    }
  }
</script>

<div class="bar">
  <span class="label">{sel.size}{noun} 선택</span>
  <span class="spacer"></span>
  <button type="button" class="ghost" onclick={() => selection.clear()}>선택 해제</button>
  <button type="button" class="ghost" onclick={selectAll}>전체 선택</button>
  <button type="button" class="primary" disabled={sel.size === 0 || busy} onclick={download}>
    다운로드
  </button>
</div>

<style>
  .bar {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 8px 8px 8px 16px;
  }
  .label {
    color: var(--text);
    font-weight: 600;
  }
  .spacer {
    flex: 1;
  }
</style>
