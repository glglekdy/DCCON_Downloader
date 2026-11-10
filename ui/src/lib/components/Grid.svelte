<script lang="ts">
  import { imageUrl, type Site } from '../api'
  import { settings } from '../stores/settings'
  import { selection, showView, viewState } from '../stores/view'
  import Card from './Card.svelte'
  import Thumb from './Thumb.svelte'

  // 1.3.0 과 같은 캐시 파일을 쓰도록 확장자를 고정한다 (main_window.py: 목록 썸네일 png, 움짤 포스터 jpg).
  // 실제 형식이 달라도 WebView 가 이미지 내용을 보고 디코딩한다.
  const LIST_THUMB_EXT = 'png'
  const POSTER_EXT = 'jpg'

  const animate = $derived($settings?.animate_gifs ?? true)
  const sel = $derived($selection)

  function openPkg(site: Site, id: number) {
    void showView({ kind: 'package', site, id })
  }
</script>

{#key $viewState.gen}
{#if $viewState.pkg}
  <div class="grid">
    {#each $viewState.pkg.items as item (item.sort)}
      <Card
        title={item.title || `#${item.sort}`}
        subtitle={item.ext.toUpperCase()}
        selected={sel.has(item.sort)}
        onToggle={() => selection.toggle(item.sort)}
      >
        <Thumb
          src={imageUrl(item.path)}
          ext={item.ext}
          poster={item.thumb ? { src: item.thumb, ext: POSTER_EXT } : null}
          gen={$viewState.gen}
          site={$viewState.site}
          {animate}
        />
      </Card>
    {/each}
  </div>
{:else if $viewState.rows.length}
  <div class="grid">
    {#each $viewState.rows as brief (brief.idx)}
      <Card
        title={brief.title}
        subtitle={brief.seller}
        selected={sel.has(brief.idx)}
        tooltip={`${brief.title}\n클릭: 선택 (패키지 전체 받기)\n더블클릭: 안을 열어보기`}
        checkTooltip="선택하면 패키지 전체를 받습니다"
        onToggle={() => selection.toggle(brief.idx)}
        onOpen={() => openPkg($viewState.site, brief.idx)}
      >
        <Thumb
          src={brief.thumb_url}
          ext={LIST_THUMB_EXT}
          gen={$viewState.gen}
          site={$viewState.site}
          animate={false}
        />
      </Card>
    {/each}
  </div>
{/if}
{/key}

<style>
  .grid {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    padding: 4px 22px 24px;
  }
</style>
