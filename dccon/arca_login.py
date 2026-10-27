"""아카라이브 로그인. 실제 Chrome(없으면 Edge)을 띄워 사용자가 직접 로그인하게 한다.

앱에 브라우저 엔진을 넣으면 100MB 넘게 커진다. 대신 설치된 브라우저를
앱 전용 프로필 + 원격 디버깅 포트로 띄우고, 로그인이 끝나면 DevTools
프로토콜로 쿠키를 꺼낸 뒤 창을 닫는다.

- Chrome 136+ 는 기본 프로필에서 원격 디버깅을 막는다. 그래서 전용 프로필을 쓴다.
- cf_clearance 쿠키는 User-Agent 에 묶인다. 그 브라우저의 UA 를 같이 저장해 쓴다.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import httpx

from .arca import ARCA_BASE
from .client import CancelledError
from .config import ARCA_PROFILE_DIR, ARCA_SESSION_PATH

LOGIN_URL = f"{ARCA_BASE}/u/login?goto=/e/"


class LoginError(RuntimeError):
    pass


@dataclass
class ArcaSession:
    user_agent: str
    cookies: list[dict] = field(default_factory=list)

    def jar(self) -> httpx.Cookies:
        jar = httpx.Cookies()
        for c in self.cookies:
            jar.set(c["name"], c["value"], domain=c.get("domain", ""), path=c.get("path", "/"))
        return jar

    def save(self, path: Path = ARCA_SESSION_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path = ARCA_SESSION_PATH) -> "ArcaSession | None":
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return cls(user_agent=raw["user_agent"], cookies=list(raw["cookies"]))
        except (OSError, ValueError, KeyError, TypeError):
            return None

    @staticmethod
    def forget(path: Path = ARCA_SESSION_PATH) -> None:
        try:
            path.unlink()
        except OSError:
            pass


def find_browser() -> str | None:
    roots = [os.environ.get(k) for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
    candidates = [
        Path(root) / rel
        for rel in ("Google/Chrome/Application/chrome.exe",
                    "Microsoft/Edge/Application/msedge.exe")
        for root in roots if root
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def _cdp(ws_url: str, method: str, params: dict | None = None) -> dict:
    import websocket

    # Origin 헤더를 보내면 Chrome 이 --remote-allow-origins 없이는 거절한다.
    ws = websocket.create_connection(ws_url, timeout=10, suppress_origin=True)
    try:
        ws.send(json.dumps({"id": 1, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == 1:
                return msg.get("result") or {}
    finally:
        ws.close()


def _is_logged_in(session: ArcaSession) -> bool:
    try:
        resp = httpx.get(f"{ARCA_BASE}/e/", cookies=session.jar(), follow_redirects=True,
                         headers={"User-Agent": session.user_agent}, timeout=15)
    except httpx.HTTPError:
        return False
    return resp.status_code == 200 and "/u/login" not in resp.url.path


def _wait_port(profile: Path, cancel: threading.Event, timeout: float = 20) -> int:
    marker = profile / "DevToolsActivePort"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cancel.is_set():
            raise CancelledError()
        try:
            return int(marker.read_text().split()[0])
        except (OSError, ValueError, IndexError):
            time.sleep(0.3)
    raise LoginError("브라우저를 띄우지 못했습니다.")


def login(cancel: threading.Event, timeout: float = 600) -> ArcaSession:
    """로그인이 끝날 때까지 막는다. 워커 스레드에서 부른다."""
    exe = find_browser()
    if exe is None:
        raise LoginError("Chrome 또는 Edge 를 찾을 수 없습니다.")
    ARCA_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        (ARCA_PROFILE_DIR / "DevToolsActivePort").unlink()
    except OSError:
        pass
    subprocess.Popen([
        exe, f"--user-data-dir={ARCA_PROFILE_DIR}", "--remote-debugging-port=0",
        "--no-first-run", "--no-default-browser-check", "--new-window", LOGIN_URL,
    ])
    port = _wait_port(ARCA_PROFILE_DIR, cancel)
    local = httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=5)

    deadline = time.monotonic() + timeout
    last_check = 0.0
    try:
        while time.monotonic() < deadline:
            if cancel.is_set():
                raise CancelledError()
            time.sleep(1)
            try:
                pages = local.get("/json/list").json()
            except (httpx.HTTPError, ValueError):
                raise LoginError("로그인하기 전에 브라우저 창이 닫혔습니다.") from None
            urls = [p.get("url", "") for p in pages if p.get("type") == "page"]
            # 로그인 화면을 벗어나 아카라이브에 있을 때만 쿠키를 확인한다.
            if not any(u.startswith(ARCA_BASE) and "/u/login" not in u for u in urls):
                continue
            if time.monotonic() - last_check < 3:
                continue
            last_check = time.monotonic()
            version = local.get("/json/version").json()
            ws_url = version["webSocketDebuggerUrl"]
            raw = _cdp(ws_url, "Storage.getCookies").get("cookies", [])
            session = ArcaSession(
                user_agent=version.get("User-Agent", ""),
                cookies=[
                    {k: c[k] for k in ("name", "value", "domain", "path")}
                    for c in raw if c.get("domain", "").lstrip(".").endswith("arca.live")
                ],
            )
            if session.cookies and _is_logged_in(session):
                try:
                    _cdp(ws_url, "Browser.close")
                except Exception:  # noqa: BLE001 - 창이 안 닫혀도 로그인은 끝났다
                    pass
                return session
        raise LoginError("로그인 시간이 지났습니다. 다시 시도해 주세요.")
    finally:
        local.close()
