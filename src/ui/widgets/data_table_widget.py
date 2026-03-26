from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget


class DataTableWidget(QWidget):
    POINT_COUNT = 128

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._table = QTableWidget(self.POINT_COUNT, 2, self)
        self._table.setHorizontalHeaderLabels(["像素点", "灰度值"])
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.setStyleSheet(
            "QTableWidget { background-color: #111111; color: #EAEAEA; gridline-color: #2A2A2A; border: 1px solid #2A2A2A; alternate-background-color: #181818; }"
            "QHeaderView::section { background-color: #1E1E1E; color: #EAEAEA; border: 1px solid #2A2A2A; padding: 4px; }"
        )

        self._summary = QLabel("最大值: 0 (位置: 0) | 最小值: 0 (位置: 0)", self)
        self._summary.setStyleSheet("color: #EAEAEA;")

        self._value_items: list[QTableWidgetItem] = []

        for index in range(self.POINT_COUNT):
            index_item = QTableWidgetItem(str(index))
            value_item = QTableWidgetItem("0")
            index_item.setTextAlignment(int(Qt.AlignmentFlag.AlignCenter))
            value_item.setTextAlignment(int(Qt.AlignmentFlag.AlignCenter))
            self._table.setItem(index, 0, index_item)
            self._table.setItem(index, 1, value_item)
            self._value_items.append(value_item)

        layout.addWidget(self._table)
        layout.addWidget(self._summary)

    def update_data(self, data: list[int]) -> None:
        normalized = [max(0, min(255, int(value))) for value in data[: self.POINT_COUNT]]
        if len(normalized) < self.POINT_COUNT:
            normalized.extend([0] * (self.POINT_COUNT - len(normalized)))

        max_value = max(normalized)
        min_value = min(normalized)
        max_pos = normalized.index(max_value)
        min_pos = normalized.index(min_value)

        for index, value in enumerate(normalized):
            self._value_items[index].setText(str(value))
            if index == max_pos:
                self._value_items[index].setForeground(QColor("#FF5252"))
            elif index == min_pos:
                self._value_items[index].setForeground(QColor("#40C4FF"))
            else:
                self._value_items[index].setForeground(QColor("#EAEAEA"))

        self._summary.setText(f"最大值: {max_value} (位置: {max_pos}) | 最小值: {min_value} (位置: {min_pos})")
