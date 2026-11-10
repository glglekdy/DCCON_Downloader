<script lang="ts">
  import { extFromUrl, imageUrl, type Site } from '../api'
  import { settings } from '../stores/settings'
  import { selection, showView, viewState } from '../stores/view'
  import Card from './Card.svelte'
  import Thumb from './Thumb.svelte'

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
          poster={item.thumb ? { src: item.thumb, ext: extFromUrl(item.thumb) } : null}
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
          ext={extFromUrl(brief.thumb_url)}
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
