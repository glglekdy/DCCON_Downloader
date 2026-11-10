<script lang="ts">
  let { active = false }: { active?: boolean } = $props()
</script>

<!-- 받는 동안 바닥에서 번지는 빛 (glow.py). 켜질 때 420ms, 꺼질 때 520ms, 켜진 뒤엔 2.6초 주기로 숨쉰다. -->
<div class="glow" class:active aria-hidden="true">
  <div class="pulse"></div>
</div>

<style>
  .glow {
    --boost: 1;
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    height: 260px;
    pointer-events: none;
    opacity: 0;
    transition: opacity 520ms cubic-bezier(0.215, 0.61, 0.355, 1);
  }
  .glow.active {
    opacity: 1;
    transition-duration: 420ms;
  }
  .pulse {
    position: absolute;
    inset: 0;
    background: linear-gradient(
      to top,
      color-mix(in srgb, var(--glow) calc(26% * var(--boost)), transparent) 0%,
      color-mix(in srgb, var(--glow) calc(13% * var(--boost)), transparent) 38%,
      color-mix(in srgb, var(--glow) calc(4% * var(--boost)), transparent) 72%,
      transparent 100%
    );
  }
  .active .pulse {
    animation: breathe 2600ms ease-in-out 420ms infinite;
  }
  @keyframes breathe {
    0%,
    100% {
      opacity: 0.72;
    }
    50% {
      opacity: 1;
    }
  }
  /* 어두운 바탕에서는 같은 알파가 묻힌다. */
  :global(:root[data-theme='dark']) .glow {
    --boost: 1.5;
  }
  @media (prefers-color-scheme: dark) {
    :global(:root:not([data-theme])) .glow {
      --boost: 1.5;
    }
  }
  :global(:root[data-reduce-motion]) .active .pulse {
    animation: none;
  }
</style>
