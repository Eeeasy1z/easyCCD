from __future__ import annotations

import csv
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


class PlaybackCsvCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = MainWindow()

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()

    def _write_csv(self, rows: list[list[str]]) -> Path:
        file_path = Path(tempfile.gettempdir()) / "easyccd_playback_test.csv"
        with file_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerows(rows)
        return file_path

    def test_load_v1_schema_csv(self) -> None:
        header = ["schema_version", "帧号", "时间戳"] + [f"像素{i}" for i in range(128)]
        row = ["v1", "11", "1700000000.1"] + [str(i % 256) for i in range(128)]
        file_path = self._write_csv([header, row])

        with patch("ui.controllers.playback_controller.QFileDialog.getOpenFileName", return_value=(str(file_path), "CSV 文件 (*.csv)")):
            self.window._load_playback_csv()

        self.assertEqual(len(self.window._playback_frames), 1)
        self.assertEqual(self.window._playback_frames[0][0], 11)
        self.assertEqual(len(self.window._playback_frames[0][2]), 128)

    def test_load_v2_schema_csv(self) -> None:
        header = ["schema_version", "批次", "帧号", "时间戳"] + [f"像素{i}" for i in range(128)]
        row = ["v2", "1", "22", "1700000000.2"] + [str((i + 1) % 256) for i in range(128)]
        file_path = self._write_csv([header, row])

        with patch("ui.controllers.playback_controller.QFileDialog.getOpenFileName", return_value=(str(file_path), "CSV 文件 (*.csv)")):
            self.window._load_playback_csv()

        self.assertEqual(len(self.window._playback_frames), 1)
        self.assertEqual(self.window._playback_frames[0][0], 22)
        self.assertEqual(len(self.window._playback_frames[0][2]), 128)

    def test_load_v2_multi_batch_sorted_by_global_timeline(self) -> None:
        header = ["schema_version", "批次", "帧号", "时间戳"] + [f"像素{i}" for i in range(128)]
        row_batch2_late = ["v2", "2", "201", "1700000001.000000"] + [str((i + 2) % 256) for i in range(128)]
        row_batch1_early = ["v2", "1", "101", "1700000000.500000"] + [str((i + 1) % 256) for i in range(128)]
        row_batch2_earlier = ["v2", "2", "200", "1700000000.600000"] + [str((i + 3) % 256) for i in range(128)]
        file_path = self._write_csv([header, row_batch2_late, row_batch1_early, row_batch2_earlier])

        with patch("ui.controllers.playback_controller.QFileDialog.getOpenFileName", return_value=(str(file_path), "CSV 文件 (*.csv)")):
            self.window._load_playback_csv()

        self.assertEqual([frame[0] for frame in self.window._playback_frames], [101, 200, 201])
        self.assertEqual(self.window._playback_batch_ids, [1, 2, 2])
