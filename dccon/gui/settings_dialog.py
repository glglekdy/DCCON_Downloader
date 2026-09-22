"""설정 창."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
)

from ..cache import ImageCache
from ..config import Settings


def human_size(num: int) -> str:
    step = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if step < 1024 or unit == "GB":
            return f"{step:,.0f} {unit}" if unit == "B" else f"{step:,.1f} {unit}"
        step /= 1024
    return f"{step:,.1f} GB"


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, cache: ImageCache, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("설정")
        self.setMinimumWidth(520)
        self._settings = settings
        self._cache = cache

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(22)
        title = QLabel("다운로드 설정")
        title.setObjectName("crumb")
        outer.addWidget(title)
        form = QFormLayout()
        form.setSpacing(10)

        # 저장 폴더
        dir_row = QHBoxLayout()
        self.dir_edit = QLineEdit(settings.download_dir)
        browse = QPushButton("찾아보기…")
        browse.clicked.connect(self._pick_dir)
        dir_row.addWidget(self.dir_edit, 1)
        dir_row.addWidget(browse)
        form.addRow("저장 폴더", dir_row)

        # 동시 다운로드 수
        conc_row = QHBoxLayout()
        self.conc_slider = QSlider(Qt.Orientation.Horizontal)
        self.conc_slider.setRange(1, 16)
        self.conc_slider.setValue(settings.concurrency)
        self.conc_label = QLabel(str(settings.concurrency))
        self.conc_label.setFixedWidth(24)
        self.conc_slider.valueChanged.connect(
            lambda v: self.conc_label.setText(str(v))
        )
        conc_row.addWidget(self.conc_slider, 1)
        conc_row.addWidget(self.conc_label)
        form.addRow("동시 다운로드", conc_row)

        hint = QLabel("3~4 권장. 높이면 빨라지지만 차단 위험이 올라갑니다.")
        hint.setObjectName("hint")
        form.addRow("", hint)

        self.main_img = QCheckBox("패키지 대표 이미지도 저장 (_main)")
        self.main_img.setChecked(settings.save_main_image)
        form.addRow("", self.main_img)

        self.meta = QCheckBox("_meta.json 으로 제목·태그 정보 남기기")
        self.meta.setChecked(settings.write_meta_json)
        form.addRow("", self.meta)

        self.reduce_motion = QCheckBox("움직임 줄이기 (애니메이션 끄기)")
        self.reduce_motion.setChecked(settings.reduce_motion)
        form.addRow("화면 효과", self.reduce_motion)

        outer.addLayout(form)

        # 캐시
        cache_row = QHBoxLayout()
        self.cache_label = QLabel("계산 중…")
        clear = QPushButton("비우기")
        clear.clicked.connect(self._clear_cache)
        cache_row.addWidget(self.cache_label, 1)
        cache_row.addWidget(clear)
        outer.addLayout(cache_row)
        self._refresh_cache_label()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("저장")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("primary")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _pick_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "저장 폴더 선택", self.dir_edit.text()
        )
        if chosen:
            self.dir_edit.setText(chosen)

    def _refresh_cache_label(self) -> None:
        count, total = self._cache.stats()
        self.cache_label.setText(f"캐시: {human_size(total)}  (이미지 {count:,}개)")

    def _clear_cache(self) -> None:
        confirm = QMessageBox.question(
            self,
            "캐시 비우기",
            "받아둔 미리보기 이미지를 전부 지웁니다.\n"
            "저장 폴더의 파일은 그대로 남습니다. 계속할까요?",
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self._cache.clear()
            self._refresh_cache_label()

    def apply_to(self, settings: Settings) -> None:
        settings.download_dir = self.dir_edit.text().strip() or settings.download_dir
        settings.concurrency = self.conc_slider.value()
        settings.save_main_image = self.main_img.isChecked()
        settings.write_meta_json = self.meta.isChecked()
        settings.reduce_motion = self.reduce_motion.isChecked()
        Path(settings.download_dir).mkdir(parents=True, exist_ok=True)
