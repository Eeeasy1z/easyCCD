from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


class SerialNonBlockingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = MainWindow()

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()

    def test_wrong_com_connect_is_non_blocking_and_recovers(self) -> None:
        self.window._port_combo.clear()
        self.window._port_combo.addItem("COM_NOT_EXIST")

        with patch.object(self.window._serial_manager, "open", side_effect=RuntimeError("open failed")):
            t0 = time.time()
            self.window._toggle_connection()
            click_elapsed = time.time() - t0

            self.assertLess(click_elapsed, 0.05)

            timeout = time.time() + 1.0
            while time.time() < timeout and not self.window._connect_button.isEnabled():
                self.app.processEvents()
                time.sleep(0.01)

            self.assertTrue(self.window._connect_button.isEnabled())
            self.assertFalse(self.window._connected)
            self.assertIn("连接失败", self.window._status_label.text())
