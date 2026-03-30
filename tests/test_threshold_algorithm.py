from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from core.threshold import (
    THRESHOLD_METHOD_FIXED,
    THRESHOLD_METHOD_GRADIENT,
    THRESHOLD_METHOD_ITERATIVE,
    THRESHOLD_METHOD_MEAN,
    THRESHOLD_METHOD_OTSU,
    THRESHOLD_METHOD_PERCENTILE,
    compute_threshold,
)


class ThresholdAlgorithmTests(unittest.TestCase):
    def test_fixed_threshold_uses_fixed_value(self) -> None:
        payload = [0, 10, 20, 30]
        self.assertEqual(compute_threshold(payload, THRESHOLD_METHOD_FIXED, fixed_value=140), 140)

    def test_mean_threshold_matches_average(self) -> None:
        payload = [0, 0, 100, 100]
        self.assertEqual(compute_threshold(payload, THRESHOLD_METHOD_MEAN, fixed_value=128), 50)

    def test_otsu_threshold_for_two_peaks(self) -> None:
        payload = ([20] * 40) + ([210] * 40)
        result = compute_threshold(payload, THRESHOLD_METHOD_OTSU, fixed_value=128)
        self.assertGreaterEqual(result, 20)
        self.assertLess(result, 210)

    def test_iterative_threshold_between_clusters(self) -> None:
        payload = ([30] * 30) + ([180] * 30)
        result = compute_threshold(payload, THRESHOLD_METHOD_ITERATIVE, fixed_value=128)
        self.assertGreater(result, 30)
        self.assertLess(result, 180)

    def test_percentile_threshold_returns_median_like_value(self) -> None:
        payload = [0, 50, 100, 150, 200]
        result = compute_threshold(payload, THRESHOLD_METHOD_PERCENTILE, fixed_value=128)
        self.assertEqual(result, 100)

    def test_gradient_threshold_uses_strongest_1d_edge(self) -> None:
        payload = [10, 11, 9, 12, 13, 120, 140, 160, 161, 162]
        result = compute_threshold(payload, THRESHOLD_METHOD_GRADIENT, fixed_value=128)
        self.assertGreaterEqual(result, 40)
        self.assertLessEqual(result, 150)

    def test_gradient_threshold_window_radius_changes_result(self) -> None:
        payload = [5, 6, 7, 8, 10, 120, 200, 210, 220, 230, 240]
        result_small = compute_threshold(payload, THRESHOLD_METHOD_GRADIENT, gradient_window_radius=1)
        result_large = compute_threshold(payload, THRESHOLD_METHOD_GRADIENT, gradient_window_radius=4)
        self.assertNotEqual(result_small, result_large)


if __name__ == "__main__":
    unittest.main()
