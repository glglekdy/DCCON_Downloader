<script lang="ts">
  import { cancelQueue, isCmdError, pauseQueue } from '../api'
  import { showNotice } from '../stores/notice'
  import { percentOf, queue, rowText, statusLine } from '../stores/queue'

  let expanded = $state(false)
  const q = $derived($queue)
  const pct = $derived(percentOf(q))
  const rows = $derived([...q.jobs.values()])

  function fail(e: unknown) {
    showNotice(isCmdError(e) ? e.message : String(e))
  }

  /** 일시정지·중단 호출이 돌아오기 전에 다시 누르지 못하게 한다. */
  let busy = $state(false)

  async function togglePause() {
    if (busy) return
    busy = true
    const next = !q.paused
    try {
      await pauseQueue(next)
      queue.setPaused(next)
    } catch (e) {
      fail(e)
    } finally {
      busy = false
    }
  }

  async function cancel() {
    if (busy) return
    busy = true
    // 파이썬판처럼 바로 "중단하는 중…" 을 보이고, 마지막 상태는 queue-finished 가 가져온다.
    queue.markCancelling()
    try {
      await cancelQueue()
    } catch (e) {
      // 중단이 안 됐으니 되돌리고 알린다.
      queue.clearCancelling()
      fail(e)
    } finally {
      busy = false
    }
  }
</script>

<div class="queue">
  <div class="detail" class:open={expanded}>
    <div class="detail-inner">
      <div class="table" role="table" aria-label="패키지별 진행 내역">
        <div class="tr thead" role="row">
          <span role="columnheader">패키지</span><span role="columnheader">상태</span>
        </div>
        {#each rows as j}
          <div class="tr" role="row">
            <span class="title" role="cell" title={j.title}>{j.title}</span>
            <span class="state" role="cell">{rowText(j)}</span>
          </div>
        {/each}
      </div>
    </div>
  </div>

  <div class="row">
    <div class="text">
      <div class="head">
        <span class="status">{statusLine(q)}</span>
        <span class="percent">{pct}%</span>
      </div>
      <div
        class="track"
        role="progressbar"
        aria-label="전체 다운로드 진행률"
        aria-valuemin="0"
        aria-valuemax="100"
        aria-valuenow={pct}
      >
        <div class="chunk" style:width="{pct}%"></div>
      </div>
    </div>
    <button
      type="button"
      class="ghost"
      class:on={expanded}
      title="패키지별 진행 내역 펼치기 / 접기"
      aria-label="다운로드 내역 펼치기 / 접기"
      aria-expanded={expanded}
      onclick={() => (expanded = !expanded)}>내역</button
    >
    {#if q.running}
      <button type="button" class="ghost" disabled={q.cancelling || busy} onclick={togglePause}>
        {q.paused ? '재개' : '일시정지'}
      </button>
      <button type="button" disabled={q.cancelling || busy} onclick={cancel}>중단</button>
    {:else}
      <button type="button" class="primary" onclick={() => queue.dismiss()}>확인</button>
    {/if}
  </div>
</div>

<style>
  .queue {
    display: flex;
    flex-direction: column;
  }
  .detail {
    display: grid;
    grid-template-rows: 0fr;
    transition: grid-template-rows 240ms cubic-bezier(0.215, 0.61, 0.355, 1);
  }
  .detail.open {
    grid-template-rows: 1fr;
  }
  .detail-inner {
    min-height: 0;
    overflow: hidden;
  }
  /* QTreeWidget#queueDetail: 펼치면 늘 170px, 첫 열 300px, 줄 바꿈 색 없음.
     머리글은 12px (QHeaderView::section padding 6px 8px), 항목은 13px (QTreeWidget::item padding 6px). */
  .table {
    height: 170px;
    overflow-y: auto;
    background: var(--tree-bg);
    font-size: 13px;
  }
  .tr {
    display: grid;
    grid-template-columns: 300px minmax(0, 1fr);
  }
  .tr > span {
    padding: 6px 8px;
    line-height: 17px;
  }
  .tr.thead {
    position: sticky;
    top: 0;
    background: var(--header-bg);
    color: var(--header-fg);
    font-size: 12px;
  }
  /* 머리글 칸 높이 33 (1.3.0 실측) */
  .tr.thead > span {
    line-height: 21px;
  }
  .title,
  .state {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  /* "2/11  01_11.gif", "저장 25  건너뜀 3" 의 두 칸 띄움을 살린다. */
  .state {
    white-space: pre;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 8px 8px 8px 16px;
  }
  .text {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-right: 8px;
  }
  .head {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .status {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--text);
    font-size: 12px;
    font-weight: 500;
  }
  .percent {
    color: var(--percent);
    font-size: 12px;
    font-weight: 600;
  }
  .track {
    height: 4px;
    border-radius: 3px;
    background: var(--dl-track);
    overflow: hidden;
  }
  .chunk {
    height: 100%;
    border-radius: 3px;
    background: var(--accent);
    transition: width 260ms cubic-bezier(0.215, 0.61, 0.355, 1);
  }
  button.on {
    background: var(--btn-hover-bg);
    color: var(--text);
  }
</style>
