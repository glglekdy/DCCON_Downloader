"""QThreadPool 위에 올리는 백그라운드 작업들.

GUI 스레드에서는 위젯만 건드리고, 네트워크는 전부 여기서 돈다.
결과는 Qt 시그널로만 넘긴다.

주의: QThreadPool.start() 에 넘긴 QRunnable 은 C++ 쪽만 수명이 보장되고
파이썬 객체는 그대로 GC 대상이 된다. 딸린 signals 객체가 같이 사라지면
emit 이 아무데도 도착하지 않는다. 그래서 작업이 끝날 때까지 호출자가
반드시 참조를 들고 있어야 한다 (`finished` 시그널로 풀어주면 된다).
"""

from __future__ import annotations

import threading
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


def _emit(signal, *args) -> None:
    """앱이 닫히는 중이면 시그널 객체가 이미 사라졌을 수 있다."""
    try:
        signal.emit(*args)
    except RuntimeError:
        pass


class TaskSignals(QObject):
    done = Signal(object)
    error = Signal(str)
    progress = Signal(int, int, str)
    finished = Signal(object)  # 참조 해제용. 인자는 Task 자신.


class Task(QRunnable):
    """함수 하나를 백그라운드에서 돌리고 결과를 시그널로 보낸다."""

    def __init__(self, fn: Callable, *args, parent: QObject | None = None,
                 **kwargs) -> None:
        super().__init__()
        self.signals = TaskSignals(parent)
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        try:
            result = self._fn(*self._args, **self._kwargs)
        except Exception as exc:  # noqa: BLE001 - UI로 올려서 보여준다
            _emit(self.signals.error, str(exc) or exc.__class__.__name__)
        else:
            _emit(self.signals.done, result)
        finally:
            _emit(self.signals.finished, self)


class ThumbSignals(QObject):
    # (generation, key, image bytes)
    loaded = Signal(int, str, bytes)
    finished = Signal(object)


class ThumbTask(QRunnable):
    """썸네일 한 장. generation이 바뀌면 결과는 UI에서 버려진다."""

    def __init__(self, signals: ThumbSignals, generation: int, key: str,
                 fetch: Callable[[], bytes]) -> None:
        super().__init__()
        self.signals = signals
        self._generation = generation
        self._key = key
        self._fetch = fetch
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        try:
            data = self._fetch()
        except Exception:  # noqa: BLE001 - 썸네일 실패는 조용히 넘긴다
            data = b""
        if data:
            _emit(self.signals.loaded, self._generation, self._key, data)
        _emit(self.signals.finished, self)


class DownloadSignals(QObject):
    item_progress = Signal(int, int, int, str)   # package_idx, done, total, name
    package_done = Signal(object)                # DownloadResult
    package_error = Signal(int, str)             # package_idx, message
    all_done = Signal()


class CancelToken:
    def __init__(self) -> None:
        self.event = threading.Event()

    def cancel(self) -> None:
        self.event.set()

    @property
    def cancelled(self) -> bool:
        return self.event.is_set()
