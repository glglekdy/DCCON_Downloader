<script lang="ts">
  import { imgUrl, type Site } from '../api'

  interface Props {
    /** 원본 주소와 확장자. */
    src: string
    ext: string
    /** 영상일 때 대신 보여줄 포스터. */
    poster?: { src: string; ext: string } | null
    gen: number
    site: Site
    animate: boolean
  }
  let { src, ext, poster = null, gen, site, animate }: Props = $props()

  const lower = $derived(ext.toLowerCase())
  const isVideo = $derived(lower === 'mp4' || lower === 'webm')
  const isGif = $derived(lower === 'gif')

  let failed = $state(false)
  /** 그림이 뜨기 전에는 1.3.0 처럼 가운데 ··· 를 보인다 (cards.Preview). 못 받으면 그대로 남는다. */
  let loaded = $state(false)
  let canvas: HTMLCanvasElement | undefined = $state()

  // 지난 세대의 요청은 백엔드가 204 로 답한다. 깨진 그림 대신 자리표시 배경을 둔다.
  const posterUrl = $derived(poster ? imgUrl(poster.src, poster.ext, gen, site) : null)
  const mainUrl = $derived(imgUrl(src, ext, gen, site))

  // GIF 를 움직이지 않을 때는 첫 프레임만 canvas 에 그린다.
  $effect(() => {
    if (!(isGif && !animate) || !canvas) return
    const target = canvas
    const img = new Image()
    img.onload = () => {
      const scale = Math.min(144 / img.naturalWidth, 144 / img.naturalHeight)
      const w = Math.max(1, Math.round(img.naturalWidth * scale))
      const h = Math.max(1, Math.round(img.naturalHeight * scale))
      const dpr = window.devicePixelRatio || 1
      target.width = Math.max(1, Math.round(w * dpr))
      target.height = Math.max(1, Math.round(h * dpr))
      target.style.width = `${w}px`
      target.style.height = `${h}px`
      target.getContext('2d')?.drawImage(img, 0, 0, target.width, target.height)
      loaded = true
    }
    img.onerror = () => (failed = true)
    img.src = mainUrl
    return () => {
      img.onload = null
      img.onerror = null
    }
  })
</script>

<div class="thumb">
  {#if !loaded}<span class="dots" aria-hidden="true">···</span>{/if}
  {#if failed}
    <!-- 자리표시 배경만 -->
  {:else if isVideo && animate}
    <video
      src={mainUrl}
      poster={posterUrl ?? undefined}
      autoplay
      loop
      muted
      playsinline
      onloadeddata={() => (loaded = true)}
      onerror={() => (failed = true)}
    ></video>
  {:else if isVideo}
    {#if posterUrl}
      <img src={posterUrl} alt="" loading="lazy" decoding="async" onload={() => (loaded = true)} onerror={() => (failed = true)} />
    {/if}
  {:else if isGif && !animate}
    <canvas bind:this={canvas}></canvas>
  {:else}
    <img src={mainUrl} alt="" loading="lazy" decoding="async" onload={() => (loaded = true)} onerror={() => (failed = true)} />
  {/if}
</div>

<style>
  .thumb {
    width: 144px;
    height: 144px;
    border-radius: 6px;
    background: var(--thumb-bg);
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    position: relative;
  }
  .dots {
    position: absolute;
    color: var(--thumb-fg);
    font-size: 26px;
  }
  /* 1.3.0 은 작은 이미지도 144px 칸에 맞춰 키운다 (cards.Preview.set_source, KeepAspectRatio). */
  img,
  video {
    width: 100%;
    height: 100%;
    object-fit: contain;
    display: block;
  }
  canvas {
    display: block;
  }
</style>
