from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class BinaryPreviewWidget(QWidget):
    POINT_COUNT = 128

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._title = QLabel("二值化结果（预留区）", self)
        self._title.setStyleSheet("color: #EAEAEA;")

        self._strip = QLabel("尚未启用二值化渲染", self)
        self._strip.setMinimumHeight(42)
        self._strip.setStyleSheet(
            "QLabel { background-color: #111111; color: #9E9E9E; border: 1px solid #2A2A2A; padding: 8px; }"
        )

        layout.addWidget(self._title)
        layout.addWidget(self._strip)

    def update_from_payload(self, payload: list[int], threshold: int = 128) -> None:
        normalized = [max(0, min(255, int(value))) for value in payload[: self.POINT_COUNT]]
        if len(normalized) < self.POINT_COUNT:
            normalized.extend([0] * (self.POINT_COUNT - len(normalized)))
        bits = ["█" if value >= threshold else "·" for value in normalized]
        chunks = ["".join(bits[i : i + 32]) for i in range(0, 128, 32)]
        self._strip.setText("\n".join(chunks))
