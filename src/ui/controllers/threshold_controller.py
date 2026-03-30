from __future__ import annotations

from core.threshold import (
    THRESHOLD_METHOD_GRADIENT,
    THRESHOLD_METHOD_ITERATIVE,
    compute_threshold,
)


class ThresholdController:
    def __init__(self, window) -> None:
        self._window = window

    def _update_gradient_control_state(self) -> None:
        enabled = self._window._threshold_mode == "auto" and str(self._window._threshold_method) == THRESHOLD_METHOD_GRADIENT
        self._window.set_threshold_gradient_control_enabled(enabled)

    def on_threshold_mode_changed(self, mode: str) -> None:
        self._window._threshold_mode = mode
        manual_mode = mode == "manual"
        self._window.set_threshold_method_editable(not manual_mode)
        self._window.set_threshold_manual_enabled(manual_mode)
        self._update_gradient_control_state()
        self._apply_preview_threshold()

    def on_threshold_method_changed(self, method: str) -> None:
        self._window._threshold_method = method
        self._update_gradient_control_state()
        if self._window._threshold_mode == "auto":
            self._apply_preview_threshold()

    def on_threshold_gradient_window_changed(self, value: int) -> None:
        self._window._threshold_gradient_window_radius = int(value)
        if self._window._threshold_mode == "auto" and str(self._window._threshold_method) == THRESHOLD_METHOD_GRADIENT:
            self._apply_preview_threshold()

    def toggle_threshold_invert(self) -> None:
        next_state = not bool(self._window._threshold_invert)
        self._window.set_threshold_invert_state(next_state)
        self._apply_preview_threshold()

    def on_threshold_manual_slider_changed(self, value: int) -> None:
        self._window._threshold_manual_value = int(value)
        self._window._threshold_manual_spin.blockSignals(True)
        self._window._threshold_manual_spin.setValue(int(value))
        self._window._threshold_manual_spin.blockSignals(False)
        if self._window._threshold_mode == "manual":
            self._apply_preview_threshold()

    def on_threshold_manual_spin_changed(self, value: int) -> None:
        self._window._threshold_manual_value = int(value)
        self._window._threshold_manual_slider.blockSignals(True)
        self._window._threshold_manual_slider.setValue(int(value))
        self._window._threshold_manual_slider.blockSignals(False)
        if self._window._threshold_mode == "manual":
            self._apply_preview_threshold()

    def refresh_with_payload(self, payload: list[int]) -> None:
        self._window._latest_filtered_payload = list(payload)
        self._apply_preview_threshold()

    def _resolve_threshold(self, payload: list[int]) -> tuple[int, str]:
        if self._window._threshold_mode == "manual":
            return int(self._window._threshold_manual_value), "手动"

        method = str(self._window._threshold_method)
        threshold = compute_threshold(
            payload,
            method,
            fixed_value=int(self._window._threshold_manual_value),
            gradient_window_radius=int(self._window._threshold_gradient_window_radius),
        )
        method_map = {
            "mean": "平均值",
            "otsu": "Otsu",
            THRESHOLD_METHOD_ITERATIVE: "迭代",
            "percentile": "百分位",
            THRESHOLD_METHOD_GRADIENT: "梯度",
        }
        return threshold, method_map.get(method, method)

    def _build_comparison_text(self, payload: list[int]) -> str:
        fixed_value = int(self._window._threshold_manual_value)
        gradient_radius = int(self._window._threshold_gradient_window_radius)
        mean_threshold = compute_threshold(payload, "mean", fixed_value=fixed_value)
        otsu_threshold = compute_threshold(payload, "otsu", fixed_value=fixed_value)
        iterative_threshold = compute_threshold(payload, THRESHOLD_METHOD_ITERATIVE, fixed_value=fixed_value)
        percentile_threshold = compute_threshold(payload, "percentile", fixed_value=fixed_value)
        gradient_threshold = compute_threshold(
            payload,
            THRESHOLD_METHOD_GRADIENT,
            fixed_value=fixed_value,
            gradient_window_radius=gradient_radius,
        )
        return (
            f"对比 平均:{mean_threshold} Otsu:{otsu_threshold} "
            f"迭代:{iterative_threshold} 百分位:{percentile_threshold} 梯度:{gradient_threshold}"
        )

    def _build_comparison_rows(self, payload: list[int]) -> list[tuple[str, str]]:
        fixed_value = int(self._window._threshold_manual_value)
        gradient_radius = int(self._window._threshold_gradient_window_radius)
        return [
            ("平均值", str(compute_threshold(payload, "mean", fixed_value=fixed_value))),
            ("Otsu", str(compute_threshold(payload, "otsu", fixed_value=fixed_value))),
            ("迭代", str(compute_threshold(payload, THRESHOLD_METHOD_ITERATIVE, fixed_value=fixed_value))),
            ("百分位", str(compute_threshold(payload, "percentile", fixed_value=fixed_value))),
            (
                "梯度",
                str(
                    compute_threshold(
                        payload,
                        THRESHOLD_METHOD_GRADIENT,
                        fixed_value=fixed_value,
                        gradient_window_radius=gradient_radius,
                    )
                ),
            ),
        ]

    def _apply_preview_threshold(self) -> None:
        payload = self._window._latest_filtered_payload
        if not payload:
            payload = self._window._latest_payload
        if not payload:
            self._window.set_threshold_status_text(int(self._window._threshold_manual_value), "手动")
            self._window.set_threshold_comparison_text("对比 平均:- Otsu:- 迭代:- 百分位:- 梯度:-")
            self._window.set_threshold_compare_rows([
                ("平均值", "-"),
                ("Otsu", "-"),
                ("迭代", "-"),
                ("百分位", "-"),
                ("梯度", "-"),
            ])
            return

        threshold, method_label = self._resolve_threshold(payload)
        self._window._current_threshold = int(threshold)
        self._window.set_threshold_status_text(int(threshold), method_label)
        self._window.set_threshold_comparison_text(self._build_comparison_text(payload))
        self._window.set_threshold_compare_rows(self._build_comparison_rows(payload))
        self._window._binary_preview_widget.update_from_payload(
            payload,
            threshold=int(threshold),
            invert=bool(self._window._threshold_invert),
        )
        self._window._waveform_widget.set_threshold_line(int(threshold))
