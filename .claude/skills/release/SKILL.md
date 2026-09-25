---
name: release
description: 디시콘 다운로더 새 버전을 빌드·검증해서 GitHub 릴리즈로 올린다. "릴리즈 해줘", "v1.2 배포", "새 버전 올려줘" 같은 요청에 쓴다.
---

# 릴리즈 절차

앱의 자동 업데이트(`dccon/updater.py`)는 `releases/latest` 를 보고, 자기 빌드 방식에 맞는
자산을 **확장자로** 고른다(`.exe` = onefile, `.zip` = onedir). 아래 규칙을 어기면 이미 깔린
앱들이 업데이트를 못 받는다.

## 0. 버전 정하기

사용자가 준 버전을 `X.Y.Z` 로 맞춘다 ("v1.1" → `1.1.0`, 태그 `v1.1.0`).
앱은 숫자만 비교하므로 **지금 버전보다 커야** 한다. `dccon/__init__.py` 의 `__version__` 을 확인.

## 1. 버전 올리기 (세 군데)

```bash
sed -i 's/^__version__ = ".*"/__version__ = "X.Y.Z"/' dccon/__init__.py
sed -i '0,/^version = ".*"/s//version = "X.Y.Z"/' pyproject.toml
uv lock          # uv.lock 의 프로젝트 버전도 따라 바뀐다
git diff --stat  # 세 파일이 1줄씩 바뀌었는지 확인
```

## 2. 커밋 전 검증

`.claude/CLAUDE.md` 의 "커밋하기 전에 반드시 확인" 1~3(테스트 → 두 방식 빌드 → 실행 확인)을
전부 통과시킨다. 실패하면 여기서 멈추고 고친다. 릴리즈는 **검증된 빌드로만** 올린다.

## 3. 커밋과 push

기능 변경과 버전 올림은 커밋을 나눈다. 메시지는 한국어로.

```bash
git add dccon/__init__.py pyproject.toml uv.lock
git commit -m "버전 X.Y.Z"
git push origin main
```

## 4. 자산 만들기

2번에서 만든 `dist/` 빌드를 그대로 쓴다(다시 빌드하지 않는다). `dist/release/` 에 모은다.

```bash
uv run python - <<'EOF'
import pathlib, shutil, zipfile
ver = "X.Y.Z"
out = pathlib.Path("dist/release"); shutil.rmtree(out, ignore_errors=True); out.mkdir()
src = pathlib.Path("dist/dccon-downloader")
with zipfile.ZipFile(out / f"dccon-downloader-{ver}.zip", "w",
                     zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
    for p in sorted(src.rglob("*")):
        if p.is_file():
            zf.write(p, pathlib.Path("dccon-downloader") / p.relative_to(src))
shutil.copy("dist/dccon-downloader.exe", out / f"dccon-downloader-{ver}.exe")
EOF
```

자산 이름은 `dccon-downloader-X.Y.Z.exe` / `.zip` 이다. **한글을 쓰지 말 것** -
깃허브가 자산 이름에서 비ASCII 를 지워 `1.2.2.exe` 같은 이름이 되어 버린다.
받은 exe 는 처음 실행될 때 스스로 `디시콘 다운로더.exe` 로 이름을 바꾼다
(`updater.LOCAL_NAME`). 업데이터는 확장자로 고르므로 이름 자체는 자유롭지만,
`updater.release_name()` 과 맞춰야 이름 바꾸기와 옛 파일 정리가 동작한다.
zip **안쪽**은 `dccon-downloader/` 폴더 하나로 감싸고 그 안에 exe 와 `_internal/` 이 있어야 한다.
업데이터가 실제로 쓰는 검사로 확인한다:

```bash
cp dist/release/*.zip dist/check.zip && uv run python -c "
from pathlib import Path; import shutil
from dccon import updater
root = updater._extract_onedir(Path('dist/check.zip'), Path('dist/check'))
print('OK', root.name, [p.name for p in root.glob('*.exe')])
shutil.rmtree('dist/check')"
```

## 5. 릴리즈 올리기

릴리즈 노트는 한국어로, 이전 태그 이후 커밋(`git log --oneline <이전태그>..HEAD`)을 보고
사용자 입장에서 쓴다. 받는 법 표(단일 exe / 폴더 zip)를 넣는다.

```bash
gh release create vX.Y.Z --repo glglekdy/DCCON_Downloader --target main \
  --title "vX.Y.Z" --notes-file <노트파일> \
  dist/release/dccon-downloader-X.Y.Z.exe \
  dist/release/dccon-downloader-X.Y.Z.zip
```

- `--draft` / `--prerelease` 를 붙이면 앱이 못 본다(`releases/latest` 에서 빠진다).
  사용자가 원할 때만 붙인다.

## 6. 확인

```bash
gh release view vX.Y.Z --repo glglekdy/DCCON_Downloader \
  --json isDraft,isPrerelease,assets \
  --jq '{draft: .isDraft, pre: .isPrerelease, assets: [.assets[] | {name, size, digest}]}'
```

`.exe` 와 `.zip` 두 자산이 있고 `digest` 가 `sha256:` 으로 채워져 있어야 한다(업데이터가 검증에 쓴다).
사용자에게 릴리즈 URL 을 알려준다. 저장소 공개 여부는 문서를 믿지 말고
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
