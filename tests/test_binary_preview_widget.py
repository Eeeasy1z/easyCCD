from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from PySide6.QtWidgets import QApplication

from ui.widgets.binary_preview_widget import BinaryPreviewWidget


class BinaryPreviewWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_binary_mapping_and_invert(self) -> None:
        widget = BinaryPreviewWidget()
        payload = [0, 255] * 64

        widget.update_from_payload(payload, threshold=128, invert=False)
        normal_text = widget._strip.text()
        self.assertIn("█", normal_text)
        self.assertIn(" ", normal_text)

        widget.update_from_payload(payload, threshold=128, invert=True)
        inverted_text = widget._strip.text()
        self.assertNotEqual(normal_text, inverted_text)


if __name__ == "__main__":
    unittest.main()
