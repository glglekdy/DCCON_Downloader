---
name: release
description: 디시콘 다운로더 새 버전을 빌드·검증해서 GitHub 릴리즈로 올린다. "릴리즈 해줘", "v2.1 배포", "새 버전 올려줘" 같은 요청에 쓴다.
---

# 릴리즈 절차

이미 깔린 1.3.0(파이썬) 앱의 자동 업데이트는 `releases/latest` 의 자산을 **확장자로** 고른다
(`.exe` = 단일 exe, `.zip` = onedir). Rust 앱도 `.exe` 를 고른다. 그래서 **자산 이름과 zip 안쪽
구조를 바꾸면 안 된다.** 어기면 이미 깔린 앱들이 업데이트를 못 받는다.

## 0. 버전 정하기

사용자가 준 버전을 `X.Y.Z` 로 맞춘다 ("v2.1" → `2.1.0`, 태그 `v2.1.0`).
앱은 숫자만 비교하므로 **지금 버전보다 커야** 한다. 루트 `Cargo.toml` 의
`[workspace.package] version` 을 확인.

## 1. 버전 올리기 (한 군데)

루트 `Cargo.toml` 의 `[workspace.package]` `version` 만 바꾼다. 크레이트들은 이 값을 따른다.

```bash
sed -i '/^\[workspace.package\]/,/^version = /s/^version = ".*"/version = "X.Y.Z"/' Cargo.toml
cargo metadata --no-deps --format-version 1 >/dev/null   # Cargo.lock 의 크레이트 버전도 갱신
git diff --stat   # Cargo.toml, Cargo.lock 만 바뀌었는지 확인
```

## 2. 커밋 전 검증

`.claude/CLAUDE.md` 의 "커밋하기 전에 반드시 확인" 1~3(테스트 → 빌드 → 실행 확인)을
전부 통과시킨다. 실패하면 여기서 멈추고 고친다. 릴리즈는 **검증된 빌드로만** 올린다.

## 3. 커밋과 push

기능 변경과 버전 올림은 커밋을 나눈다. 메시지는 한국어로.

```bash
git add Cargo.toml Cargo.lock
git commit -m "버전 X.Y.Z"
git push origin main
```

## 4. 자산 만들기

윈도우 자산 둘은 로컬에서 만든다(2번과 같은 명령에 `-Release` 를 붙인다).

```powershell
./build.ps1 -Clean -Release
```

`dist/release/` 에 둘이 생긴다. `2>&1` 은 붙이지 않는다.

맥 zip 은 GitHub Actions 에서 만든다. 푸시한 뒤 워크플로를 돌려 아티팩트를 받는다.

```bash
gh workflow run macos.yml --repo glglekdy/DCCON_Downloader --ref main
gh run list --repo glglekdy/DCCON_Downloader --workflow macos.yml --limit 1   # run id 확인
gh run watch <run-id> --repo glglekdy/DCCON_Downloader
gh run download <run-id> --repo glglekdy/DCCON_Downloader -n dccon-downloader-macos -D dist/release
```

세 개를 모두 올린다. `.pyz` 코드 패키지는 없다(옛 앱은 코드 자산이 없으면 전체 자산을 고른다).

| 자산 | 받는 쪽 |
| --- | --- |
| `dccon-downloader-X.Y.Z.exe` | Rust 앱, 옛 파이썬 단일 exe 사용자 |
| `dccon-downloader-X.Y.Z-win64.zip` | 옛 파이썬 onedir 사용자(이전용) |
| `dccon-downloader-X.Y.Z-macos.zip` | 맥 `.app` |

- **한글을 쓰지 말 것** - 깃허브가 자산 이름에서 비ASCII 를 지운다.
- `-win64.zip` 안쪽은 `dccon-downloader/dccon-downloader.exe` 와
  `dccon-downloader/_internal/MIGRATED.txt` 뿐이다. `build.ps1 -Release` 가 만들며, 올리기 전에
  항목을 확인한다.

```powershell
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::OpenRead((Resolve-Path dist/release/dccon-downloader-X.Y.Z-win64.zip)).Entries | % FullName
```

## 5. 릴리즈 올리기

릴리즈 노트는 한국어로, 이전 태그 이후 커밋(`git log --oneline <이전태그>..HEAD`)을 보고
사용자 입장에서 쓴다. 받는 법 표(윈도우 exe / 맥 zip)를 넣는다.

```bash
gh release create vX.Y.Z --repo glglekdy/DCCON_Downloader --target main \
  --title "vX.Y.Z" --notes-file <노트파일> \
  dist/release/dccon-downloader-X.Y.Z.exe \
  dist/release/dccon-downloader-X.Y.Z-win64.zip \
  dist/release/dccon-downloader-X.Y.Z-macos.zip
```

- `--draft` / `--prerelease` 를 붙이면 앱이 못 본다(`releases/latest` 에서 빠진다).
  사용자가 원할 때만 붙인다.

## 6. 확인

```bash
gh release view vX.Y.Z --repo glglekdy/DCCON_Downloader \
  --json isDraft,isPrerelease,assets \
  --jq '{draft: .isDraft, pre: .isPrerelease, assets: [.assets[] | {name, size, digest}]}'
```

`.exe`, `-win64.zip`, `-macos.zip` 세 자산이 있고 `digest` 가 `sha256:` 으로 채워져 있어야 한다
(업데이터가 검증에 쓴다). 사용자에게 릴리즈 URL 을 알려준다. 저장소 공개 여부는 문서를 믿지 말고
`gh repo view --json visibility` 로 확인한다. 비공개면 자동 업데이트가 동작하지 않는다는
점도 함께 말한다.

## 7. 패치 릴리즈 정리 (자동)

`X.Y.0` 은 계속 남기고, `X.Y.Z` (Z > 0) 패치 릴리즈는 **다음 릴리즈가 올라오면 자동으로 지워진다.**
`.github/workflows/cleanup-patch-releases.yml` 이 릴리즈 publish 때 돌면서 처리하므로 손댈 것은 없다.

- 방금 올린 릴리즈와 최신 릴리즈는 어떤 경우에도 지우지 않는다.
- 릴리즈만 지우고 git 태그는 남긴다. 태그까지 지우려면 워크플로의 `gh release delete` 에
  `--cleanup-tag` 를 붙인다.
- 지워진 뒤에도 앱의 자동 업데이트는 `releases/latest` 만 보므로 영향이 없다.

동작을 확인하고 싶으면 `gh workflow run "패치 릴리즈 정리" --repo glglekdy/DCCON_Downloader` 로
수동 실행한다. 지울 게 없으면 전부 "보존" 으로만 찍힌다.
