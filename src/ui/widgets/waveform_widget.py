from __future__ import annotations

import pyqtgraph as pg
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget


class WaveformWidget(QWidget):
    POINT_COUNT = 128
    STAGE_COLORS = ["#00D8FF", "#FFB300", "#FF4D6D"]
    THRESHOLD_COLOR = "#C792EA"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        legend_row = QHBoxLayout()
        legend_row.setContentsMargins(2, 0, 2, 0)
        legend_row.setSpacing(14)
        self._legend_labels: list[QLabel] = []
        raw_legend = QLabel("● 原始数据", self)
        raw_legend.setStyleSheet("color: #A0A0A0;")
        self._legend_labels.append(raw_legend)
        legend_row.addWidget(raw_legend)
        for idx, color in enumerate(self.STAGE_COLORS, start=1):
            label = QLabel(f"● 滤波{idx}", self)
            label.setStyleSheet(f"color: {color};")
            label.setVisible(False)
            self._legend_labels.append(label)
            legend_row.addWidget(label)
        threshold_legend = QLabel("● 阈值线", self)
        threshold_legend.setStyleSheet(f"color: {self.THRESHOLD_COLOR};")
        self._legend_labels.append(threshold_legend)
        legend_row.addWidget(threshold_legend)
        legend_row.addStretch(1)
        layout.addLayout(legend_row)

        self._x_data = list(range(self.POINT_COUNT))
        self._plot = pg.PlotWidget(self)
        self._plot.setBackground("#111111")
        self._plot.showGrid(x=True, y=True, alpha=0.3)
        self._plot.setLabel("bottom", "像素点序号", color="#EAEAEA")
        self._plot.setLabel("left", "灰度值", color="#EAEAEA")
        self._plot.setXRange(0, 127)
        self._plot.setYRange(0, 255)
        self._plot.setLimits(xMin=0, xMax=127, yMin=0, yMax=255)
        self._raw_curve = self._plot.plot(self._x_data, [0] * self.POINT_COUNT, pen=pg.mkPen("#A0A0A0", width=1))
        self._stage_curves = [
            self._plot.plot(self._x_data, [0] * self.POINT_COUNT, pen=pg.mkPen(color, width=2))
            for color in self.STAGE_COLORS
        ]
        for curve in self._stage_curves:
            curve.hide()
        self._threshold_line = pg.InfiniteLine(
            angle=0,
            pos=128,
            pen=pg.mkPen(self.THRESHOLD_COLOR, width=1.5),
        )
        self._plot.addItem(self._threshold_line)

        layout.addWidget(self._plot)

    def update_data(self, data: list[int]) -> None:
        self.update_curves(data, data, [])

    def update_curves(
        self,
        raw_data: list[int],
        filtered_data: list[int],
        stage_curves: list[tuple[str, list[int]]] | None = None,
        threshold: int | None = None,
    ) -> None:
        raw = [max(0, min(255, int(value))) for value in raw_data[: self.POINT_COUNT]]
        filtered = [max(0, min(255, int(value))) for value in filtered_data[: self.POINT_COUNT]]
        if len(raw) < self.POINT_COUNT:
            raw.extend([0] * (self.POINT_COUNT - len(raw)))
        if len(filtered) < self.POINT_COUNT:
            filtered.extend([0] * (self.POINT_COUNT - len(filtered)))
        self._raw_curve.setData(self._x_data, raw)

        stages = stage_curves or []
        if not stages:
            stages = [("滤波1", filtered)]

        visible_count = min(len(stages), len(self._stage_curves))
        for idx, curve in enumerate(self._stage_curves):
            if idx < visible_count:
                stage_data = [max(0, min(255, int(v))) for v in stages[idx][1][: self.POINT_COUNT]]
                if len(stage_data) < self.POINT_COUNT:
                    stage_data.extend([0] * (self.POINT_COUNT - len(stage_data)))
                curve.setData(self._x_data, stage_data)
                curve.show()
            else:
                curve.hide()

        for idx in range(1, len(self._legend_labels)):
            label = self._legend_labels[idx]
            if idx <= visible_count:
                stage_name = stages[idx - 1][0]
                label.setText(f"● {stage_name}")
                label.setVisible(True)
            elif idx == len(self._legend_labels) - 1:
                label.setText("● 阈值线")
                label.setVisible(True)
            else:
                label.setVisible(False)

        if threshold is not None:
            threshold_value = max(0, min(255, int(threshold)))
            self._threshold_line.setPos(threshold_value)

    def set_threshold_line(self, threshold: int) -> None:
        threshold_value = max(0, min(255, int(threshold)))
        self._threshold_line.setPos(threshold_value)
