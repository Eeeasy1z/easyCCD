from __future__ import annotations

from PySide6.QtWidgets import QTextEdit, QVBoxLayout, QWidget


class RawStreamWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._text = QTextEdit(self)
        self._text.setReadOnly(True)
        self._text.setStyleSheet(
            "QTextEdit { background-color: #111111; color: #EAEAEA; border: 1px solid #2A2A2A; }"
        )

        root.addWidget(self._text, 1)

    def append_frame(self, frame_no: int, payload: list[int], source: str = "串口") -> None:
        _ = frame_no, source
        normalized_payload = [max(0, min(255, int(v))) for v in payload[:128]]
        if len(normalized_payload) < 128:
            normalized_payload.extend([0] * (128 - len(normalized_payload)))
        length_byte = 128
        checksum = (length_byte + sum(normalized_payload)) & 0xFF
        full_frame = [0xAA, 0x55, length_byte, *normalized_payload, checksum]
        line = " ".join(f"{value:02X}" for value in full_frame)
        self._text.append(line)
        self._trim_lines(300)
        cursor = self._text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self._text.setTextCursor(cursor)

    def _trim_lines(self, max_lines: int) -> None:
        text = self._text.toPlainText()
        lines = text.splitlines()
        if len(lines) <= max_lines:
            return
        self._text.setPlainText("\n".join(lines[-max_lines:]))
