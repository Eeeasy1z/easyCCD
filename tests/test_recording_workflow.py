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

from PySide6.QtWidgets import QApplication, QMessageBox

from ui.controllers.recording_controller import RecordingBatch
from ui.main_window import MainWindow


class RecordingWorkflowBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = MainWindow()

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()

    def test_store_batch_export_then_reload_playback(self) -> None:
        self.window._recorded_frames.append((1, 1700000000.111111, [i % 256 for i in range(128)]))
        self.window._record_started_at = 1700000000.0
        self.window._recording = True

        self.window._recording_controller.stop_recording_and_store_batch()
        self.assertEqual(len(self.window._record_batches), 1)

        export_path = Path(tempfile.gettempdir()) / "easyccd_recording_export_test.csv"
        if export_path.exists():
            export_path.unlink()

        with patch(
            "ui.controllers.recording_controller.QFileDialog.getSaveFileName",
            return_value=(str(export_path), "CSV 文件 (*.csv)"),
        ), patch("ui.controllers.recording_controller.QMessageBox.information"):
            self.window._recording_controller.export_batches()

        self.assertTrue(export_path.exists())
        self.assertEqual(len(self.window._record_batches), 0)

        with export_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            rows = list(csv.reader(csv_file))
        self.assertGreaterEqual(len(rows), 2)
        self.assertEqual(rows[0][0], "schema_version")
        self.assertEqual(rows[1][0], "v2")

        with patch(
            "ui.controllers.playback_controller.QFileDialog.getOpenFileName",
            return_value=(str(export_path), "CSV 文件 (*.csv)"),
        ):
            self.window._load_playback_csv()

        self.assertEqual(len(self.window._playback_frames), 1)
        self.assertEqual(self.window._playback_frames[0][0], 1)
        self.assertEqual(len(self.window._playback_frames[0][2]), 128)

    def test_unsaved_prompt_triggered_when_batch_exists(self) -> None:
        self.window._record_batches = [
            RecordingBatch(started_at=0.0, ended_at=1.0, frames=[(1, 1.0, [0] * 128)])
        ]
        self.window._unsaved_recording = True

        with patch(
            "ui.controllers.recording_controller.QMessageBox.question",
            return_value=QMessageBox.StandardButton.No,
        ) as question_mock:
            self.window._recording_controller.handle_unsaved_batches_on_close()

        self.assertTrue(question_mock.called)
        self.window._record_batches.clear()
        self.window._unsaved_recording = False
