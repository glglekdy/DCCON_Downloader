<script lang="ts">
  import { getVersion } from '@tauri-apps/api/app'
  import { open } from '@tauri-apps/plugin-dialog'
  import { onMount } from 'svelte'
  import {
    cacheStats,
    checkUpdate,
    clearCache,
    isCmdError,
    type ReleaseInfo,
    type Settings,
    type ThemeMode,
  } from '../api'
  import { humanSize } from '../format'
  import { showNotice } from '../stores/notice'
  import { updateSettings } from '../stores/settings'
  import Modal from './Modal.svelte'
  import UpdateDialog from './UpdateDialog.svelte'

  let { initial, onClose }: { initial: Settings; onClose: () => void } = $props()

  const THEMES: [ThemeMode, string][] = [
    ['system', '시스템 설정 따르기'],
    ['light', '라이트'],
    ['dark', '다크'],
  ]

  // 저장 전까지는 사본만 고친다. 취소하면 그대로 버린다.
  // svelte-ignore state_referenced_locally
  let draft = $state<Settings>({ ...initial })
  let version = $state('')
  let cacheLabel = $state('계산 중…')
  let updateNote = $state('')
  let checking = $state(false)
  let release = $state<ReleaseInfo | null>(null)
  let confirmClear = $state(false)
  let saving = $state(false)

  const versionLine = $derived(`버전 ${version}${updateNote ? `  ·  ${updateNote}` : ''}`)

  async function refreshCache() {
    try {
      const { files, bytes } = await cacheStats()
      cacheLabel = `캐시: ${humanSize(bytes)}  (이미지 ${files.toLocaleString('en-US')}개)`
    } catch {
      cacheLabel = '캐시: 알 수 없음'
    }
  }

  onMount(() => {
    void getVersion().then(
      (v) => (version = v),
      () => (version = ''),
    )
    void refreshCache()
  })

  async function pickDir() {
    try {
      const chosen = await open({
        directory: true,
        multiple: false,
        defaultPath: draft.download_dir,
        title: '저장 폴더 선택',
      })
      if (typeof chosen === 'string' && chosen) draft.download_dir = chosen
    } catch (e) {
      showNotice(isCmdError(e) ? e.message : String(e))
    }
  }

  async function doClear() {
    confirmClear = false
    try {
      await clearCache()
    } catch (e) {
      showNotice(isCmdError(e) ? e.message : String(e))
    }
    await refreshCache()
  }

  async function check() {
    checking = true
    updateNote = '확인 중…'
    try {
      const r = await checkUpdate(true)
      if (r === null) {
        updateNote = '최신 버전입니다'
      } else {
        updateNote = `새 버전 ${r.version} 있음`
        release = r
      }
    } catch (e) {
      updateNote = isCmdError(e) ? e.message : String(e)
    } finally {
      checking = false
    }
  }

  async function save() {
    if (saving) return
    saving = true
    try {
      await updateSettings({
        download_dir: draft.download_dir.trim() || initial.download_dir,
        concurrency: draft.concurrency,
        save_main_image: draft.save_main_image,
        write_meta_json: draft.write_meta_json,
        reduce_motion: draft.reduce_motion,
        theme: draft.theme,
        animate_gifs: draft.animate_gifs,
        check_updates: draft.check_updates,
      })
      onClose()
    } catch (e) {
      showNotice(isCmdError(e) ? e.message : String(e))
      saving = false
    }
  }
</script>

<Modal title="설정" {onClose} width={520}>
  <form
    onsubmit={(e) => {
      e.preventDefault()
      void save()
    }}
  >
    <h2 class="crumb">다운로드 설정</h2>

    <div class="field">
      <label for="s-dir">저장 폴더</label>
      <div class="row">
        <input id="s-dir" type="text" bind:value={draft.download_dir} />
        <button type="button" onclick={pickDir}>찾아보기…</button>
      </div>
    </div>

    <div class="field">
      <label for="s-conc">동시 다운로드</label>
      <div class="row">
        <input id="s-conc" type="range" min="1" max="8" bind:value={draft.concurrency} />
        <span class="num">{draft.concurrency}</span>
      </div>
    </div>
    <p class="hint">3~4 권장. 높이면 빨라지지만 차단 위험이 올라갑니다.</p>

    <div class="field">
      <span class="lbl"></span>
      <label class="check"
        ><input type="checkbox" bind:checked={draft.save_main_image} /> 패키지 대표 이미지도 저장 (_main)</label
      >
    </div>
    <div class="field">
      <span class="lbl"></span>
      <label class="check"
        ><input type="checkbox" bind:checked={draft.write_meta_json} /> _meta.json 으로 제목·태그 정보 남기기</label
      >
    </div>

    <div class="field">
      <label for="s-theme">테마</label>
      <select id="s-theme" bind:value={draft.theme}>
        {#each THEMES as [key, label] (key)}
          <option value={key}>{label}</option>
        {/each}
      </select>
    </div>

    <div class="field">
      <span class="lbl">화면 효과</span>
      <label class="check"
        ><input type="checkbox" bind:checked={draft.reduce_motion} /> 움직임 줄이기 (애니메이션 끄기)</label
      >
    </div>
    <div class="field">
      <span class="lbl"></span>
      <label class="check" title="끄면 움직이는 디시콘도 첫 장면에서 멈춰 보입니다."
        ><input type="checkbox" bind:checked={draft.animate_gifs} /> GIF 미리보기 움직이기</label
      >
    </div>

    <div class="line">
      <span class="grow">{cacheLabel}</span>
      <button type="button" onclick={() => (confirmClear = true)}>비우기</button>
    </div>

    <div class="line">
      <span class="grow">{versionLine}</span>
      <button type="button" disabled={checking} onclick={check}>업데이트 확인</button>
    </div>
    <label class="check"
      ><input type="checkbox" bind:checked={draft.check_updates} /> 시작할 때 새 버전 확인</label
    >

    <div class="buttons">
      <button type="button" onclick={onClose}>취소</button>
      <button type="submit" class="primary" disabled={saving}>저장</button>
    </div>
  </form>
</Modal>

{#if confirmClear}
  <Modal title="캐시 비우기" onClose={() => (confirmClear = false)} width={400}>
    <h2 class="crumb">캐시 비우기</h2>
    <p class="msg">
      받아둔 미리보기 이미지를 전부 지웁니다.{'\n'}저장 폴더의 파일은 그대로 남습니다. 계속할까요?
    </p>
    <div class="buttons">
      <button type="button" onclick={() => (confirmClear = false)}>아니요</button>
      <button type="button" class="primary" onclick={doClear}>예</button>
    </div>
  </Modal>
{/if}

{#if release}
  <UpdateDialog {release} {version} offerSkip={false} onClose={() => (release = null)} />
{/if}

<style>
  form {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .crumb {
    margin: 0 0 12px;
    font-size: 16px;
    font-weight: 600;
    color: var(--heading);
  }
  .field {
    display: grid;
    grid-template-columns: 92px 1fr;
    align-items: center;
    gap: 10px;
  }
  .lbl,
  .field > label:first-child {
    color: var(--muted);
    font-size: 12px;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .row input[type='text'] {
    flex: 1;
    min-width: 0;
  }
  .row input[type='range'] {
    flex: 1;
    accent-color: var(--accent);
  }
  .num {
    width: 24px;
    text-align: right;
  }
  .hint {
    margin: -4px 0 0 102px;
    color: var(--muted);
    font-size: 12px;
  }
  .check {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .line {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 12px;
  }
  .grow {
    flex: 1;
    min-width: 0;
    overflow-wrap: anywhere;
  }
  .buttons {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 16px;
  }
  .msg {
    margin: 0;
    white-space: pre-line;
  }
</style>
