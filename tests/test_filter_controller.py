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

from ui.controllers.filter_controller import FilterController
from ui.main_window import MainWindow


class FilterControllerBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = MainWindow()

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()

    def test_pipeline_max_three_steps(self) -> None:
        self.window._available_filter_combo.setCurrentIndex(0)

        for _ in range(4):
            self.window._on_add_filter_step()

        self.assertEqual(self.window._filter_pipeline_table.rowCount(), 3)
        self.assertFalse(self.window._add_filter_button.isEnabled())
        self.assertIn("最多添加 3 个滤波器", self.window._status_label.text())

    def test_normalize_window_and_sigma_ranges(self) -> None:
        self.assertEqual(FilterController._normalize_window(2), 3)
        self.assertEqual(FilterController._normalize_window(4), 5)
        self.assertEqual(FilterController._normalize_window(200), 127)

        self.assertEqual(FilterController._normalize_sigma(0), 0.1)
        self.assertEqual(FilterController._normalize_sigma(99), 20.0)
        self.assertAlmostEqual(FilterController._normalize_sigma(1.25), 1.25)

    def test_threshold_manual_controls_and_auto_otsu(self) -> None:
        self.window._on_data_received([10] * 64 + [200] * 64, frame_no=1, _timestamp=0.0)

        self.window._threshold_mode_combo.setCurrentIndex(0)
        self.window._threshold_manual_slider.setValue(90)
        self.assertEqual(self.window._current_threshold, 90)
        self.assertIn("手动", self.window._threshold_status_label.text())
        self.assertFalse(self.window._threshold_gradient_spin.isEnabled())

        self.window._on_threshold_invert_toggled()
        self.assertTrue(self.window._threshold_invert)
        self.assertIn("开", self.window._threshold_invert_button.text())
        self.window._on_threshold_invert_toggled()
        self.assertFalse(self.window._threshold_invert)
        self.assertIn("关", self.window._threshold_invert_button.text())

        self.window._threshold_mode_combo.setCurrentIndex(1)
        self.window._threshold_method_combo.setCurrentIndex(1)
        self.assertIn("Otsu", self.window._threshold_status_label.text())
        self.assertFalse(self.window._threshold_gradient_spin.isEnabled())

        gradient_index = self.window._threshold_method_combo.findData("gradient")
        self.assertGreaterEqual(gradient_index, 0)
        self.window._threshold_method_combo.setCurrentIndex(gradient_index)
        self.assertTrue(self.window._threshold_gradient_spin.isEnabled())

        compare_text = self.window._threshold_comparison_label.text()
        self.assertIn("平均", compare_text)
        self.assertIn("迭代", compare_text)
        self.assertIn("百分位", compare_text)
        self.assertIn("梯度", compare_text)
        self.assertEqual(self.window._threshold_compare_table.rowCount(), 5)
        method_cell = self.window._threshold_compare_table.item(0, 0)
        value_cell = self.window._threshold_compare_table.item(2, 1)
        self.assertIsNotNone(method_cell)
        self.assertIsNotNone(value_cell)
        if method_cell is not None:
            self.assertEqual(method_cell.text(), "平均值")
        if value_cell is not None:
            self.assertNotEqual(value_cell.text(), "-")
