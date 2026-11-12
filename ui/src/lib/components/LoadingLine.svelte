<script lang="ts">
  let { active = false }: { active?: boolean } = $props()
</script>

<!-- 1.3.0 은 다 불러오면 줄을 숨겨 자리도 없앤다. 여기서는 처음부터 자리를 차지하지 않고
     제목 위에 얹어, 불러온 뒤의 배치가 1.3.0 과 같고 불러오는 동안 2px 밀렸다 돌아오지도 않게 한다. -->
<div class="loading-line" aria-hidden="true">
  {#if active}<div class="track"><div class="chunk"></div></div>{/if}
</div>

<style>
  .loading-line {
    height: 0;
    flex: none;
    position: relative;
    z-index: 1;
  }
  .track {
    position: absolute;
    left: 0;
    right: 0;
    top: 0;
    height: 2px;
    overflow: hidden;
  }
  .chunk {
    position: absolute;
    top: 0;
    bottom: 0;
    width: 30%;
    background: var(--loading-chunk);
    animation: slide 1.1s ease-in-out infinite;
  }
  @keyframes slide {
    from {
      left: -30%;
    }
    to {
      left: 100%;
    }
  }
</style>
