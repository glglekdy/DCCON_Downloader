"""디시콘 HTTP 클라이언트.

- 이미지 CDN은 Referer가 없으면 403을 던진다. 모든 요청에 기본 헤더로 박는다.
- 스레드 여러 개가 같은 Client를 공유한다(httpx.Client는 스레드 세이프).
- 요청 간격에 지터를 섞고, 429/5xx는 지수 백오프로 물러난다.
"""

from __future__ import annotations

import random
import threading
import time

import httpx

BASE = "https://dccon.dcinside.com"
REFERER = "https://dccon.dcinside.com/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_RETRY_STATUS = {429, 500, 502, 503, 504}


class RateLimitError(RuntimeError):
    """차단으로 판단되어 물러나야 하는 상황."""


class Throttle:
    """요청 시작 시각 사이에 최소 간격을 둔다."""

    def __init__(self, min_interval: float = 0.12, jitter: float = 0.08) -> None:
        self.min_interval = min_interval
        self.jitter = jitter
        self._lock = threading.Lock()
        self._next_at = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            if now < self._next_at:
                delay = self._next_at - now
            else:
                delay = 0.0
            self._next_at = max(now, self._next_at) + self.min_interval + random.uniform(0, self.jitter)
        if delay > 0:
            time.sleep(delay)


class DcconClient:
    def __init__(self, throttle: Throttle | None = None, timeout: float = 20.0) -> None:
        self._throttle = throttle or Throttle()
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": USER_AGENT,
                "Referer": REFERER,
                "Accept-Language": "ko-KR,ko;q=0.9",
            },
            limits=httpx.Limits(max_connections=16, max_keepalive_connections=8),
        )
        # 차단을 만나면 세워두고, 풀릴 때까지 모든 워커가 여기서 기다린다.
        self._resume = threading.Event()
        self._resume.set()
        self._pause_lock = threading.Lock()

    # ---- 일시정지 제어 -------------------------------------------------
    @property
    def paused(self) -> bool:
        return not self._resume.is_set()

    def pause(self) -> None:
        self._resume.clear()

    def resume(self) -> None:
        self._resume.set()

    def _await_resume(self, cancel: threading.Event | None) -> None:
        while not self._resume.wait(timeout=0.25):
            if cancel is not None and cancel.is_set():
                raise CancelledError()

    # ---- 요청 ----------------------------------------------------------
    def request(
        self,
        method: str,
        url: str,
        *,
        retries: int = 4,
        cancel: threading.Event | None = None,
        **kwargs,
    ) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            if cancel is not None and cancel.is_set():
                raise CancelledError()
            self._await_resume(cancel)
            self._throttle.wait()
            try:
                resp = self._client.request(method, url, **kwargs)
            except httpx.HTTPError as exc:
                last_exc = exc
            else:
                if resp.status_code < 400:
                    return resp
                if resp.status_code in _RETRY_STATUS:
                    last_exc = RateLimitError(f"HTTP {resp.status_code}")
                    # 429가 이어지면 잠깐 전체를 멈추는 편이 안전하다.
                    if resp.status_code == 429:
                        self._backoff_pause()
                else:
                    resp.raise_for_status()
            if attempt < retries:
                time.sleep(min(2**attempt * 0.5, 8.0) + random.uniform(0, 0.4))
        raise last_exc or RuntimeError(f"요청 실패: {url}")

    def _backoff_pause(self) -> None:
        # 여러 워커가 동시에 429를 맞아도 한 번만 멈춘다.
        with self._pause_lock:
            if self.paused:
                return
            self.pause()
        threading.Timer(5.0, self.resume).start()

    def get(self, url: str, **kwargs) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def close(self) -> None:
        self._client.close()


class CancelledError(Exception):
    """사용자가 중단시킴."""
