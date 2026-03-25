from __future__ import annotations

import pyqtgraph as pg
from PySide6.QtWidgets import QVBoxLayout
from PySide6.QtWidgets import QWidget


class WaveformWidget(QWidget):
    POINT_COUNT = 128

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._x_data = list(range(self.POINT_COUNT))
        self._plot = pg.PlotWidget(self)
        self._plot.setBackground("#111111")
        self._plot.showGrid(x=True, y=True, alpha=0.3)
        self._plot.setLabel("bottom", "像素点序号")
        self._plot.setLabel("left", "灰度值")
        self._plot.setXRange(0, 127)
        self._plot.setYRange(0, 255)
        self._plot.setLimits(xMin=0, xMax=127, yMin=0, yMax=255)
        self._raw_curve = self._plot.plot(self._x_data, [0] * self.POINT_COUNT, pen=pg.mkPen("#A0A0A0", width=1))
        self._filtered_curve = self._plot.plot(self._x_data, [0] * self.POINT_COUNT, pen=pg.mkPen("#00D8FF", width=2))

        layout.addWidget(self._plot)

    def update_data(self, data: list[int]) -> None:
        self.update_curves(data, data)

    def update_curves(self, raw_data: list[int], filtered_data: list[int]) -> None:
        raw = [max(0, min(255, int(value))) for value in raw_data[: self.POINT_COUNT]]
        filtered = [max(0, min(255, int(value))) for value in filtered_data[: self.POINT_COUNT]]
        if len(raw) < self.POINT_COUNT:
            raw.extend([0] * (self.POINT_COUNT - len(raw)))
        if len(filtered) < self.POINT_COUNT:
            filtered.extend([0] * (self.POINT_COUNT - len(filtered)))
        self._raw_curve.setData(self._x_data, raw)
        self._filtered_curve.setData(self._x_data, filtered)
