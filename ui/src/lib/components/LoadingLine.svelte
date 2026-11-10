<script lang="ts">
  let { active = false }: { active?: boolean } = $props()
</script>

<div class="loading-line" aria-hidden="true">
  {#if active}<div class="chunk"></div>{/if}
</div>

<style>
  .loading-line {
    height: 2px;
    flex: none;
    background: transparent;
    overflow: hidden;
    position: relative;
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
