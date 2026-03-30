from __future__ import annotations

class FilterController:
    MAX_STEPS = 3

    def __init__(self, window) -> None:
        self._window = window

    def refresh_filter_step_ui(self) -> None:
        steps = self._window._filter_pipeline.get_steps()
        self._window.set_filter_pipeline_rows([step.filter_name for step in steps])

        has_steps = bool(steps)
        self._window.set_filter_controls_enabled(has_steps=has_steps, can_add=len(steps) < self.MAX_STEPS)

        if has_steps:
            self._window.select_filter_row(0)
            self.on_filter_step_selected(0)
        else:
            self._window.clear_filter_param_keys()

    def on_add_filter_step(self) -> None:
        if len(self._window._filter_pipeline.get_steps()) >= self.MAX_STEPS:
            self._window._status_label.setText("状态: 滤波管道最多添加 3 个滤波器")
            return
        filter_name = self._window._available_filter_combo.currentText().strip()
        if not filter_name:
            return
        self._window._filter_pipeline.add_step(filter_name)
        self.refresh_filter_step_ui()
        self.recompute_current_view_with_filters()

    def on_remove_filter_step(self) -> None:
        index = self._window._get_selected_filter_step_index()
        if index < 0:
            return
        self._window._filter_pipeline.remove_step(index)
        self.refresh_filter_step_ui()
        self.recompute_current_view_with_filters()

    def on_move_filter_step_up(self) -> None:
        index = self._window._get_selected_filter_step_index()
        if index <= 0:
            return
        self._window._filter_pipeline.move_up(index)
        self.refresh_filter_step_ui()
        self._window.select_filter_row(index - 1)
        self.recompute_current_view_with_filters()

    def on_move_filter_step_down(self) -> None:
        index = self._window._get_selected_filter_step_index()
        if index < 0:
            return
        self._window._filter_pipeline.move_down(index)
        self.refresh_filter_step_ui()
        self._window.select_filter_row(min(index + 1, self._window._filter_pipeline_table.rowCount() - 1))
        self.recompute_current_view_with_filters()

    def on_filter_step_selected(self, index: int) -> None:
        steps = self._window._filter_pipeline.get_steps()
        if not (0 <= index < len(steps)):
            self._window.clear_filter_param_keys()
            return
        step = steps[index]
        keys = list(step.params.keys())
        self._window.set_filter_param_keys(keys)
        if keys:
            first_key = keys[0]
            self.configure_param_editor(first_key, float(step.params[first_key]))

    def on_filter_param_key_changed(self, key: str) -> None:
        index = self._window._get_selected_filter_step_index()
        steps = self._window._filter_pipeline.get_steps()
        if not (0 <= index < len(steps)):
            return
        if key not in steps[index].params:
            return
        self.configure_param_editor(key, float(steps[index].params[key]))

    def configure_param_editor(self, key: str, value: float) -> None:
        if key == "window":
            self._window._param_value_spin.setDecimals(0)
            self._window._param_value_spin.setSingleStep(2.0)
            self._window._param_value_spin.setRange(3.0, 127.0)
            window = self._normalize_window(value)
            self._window._param_value_spin.setValue(float(window))
            return

        if key == "sigma":
            self._window._param_value_spin.setDecimals(3)
            self._window._param_value_spin.setSingleStep(0.1)
            self._window._param_value_spin.setRange(0.1, 20.0)
            sigma = self._normalize_sigma(value)
            self._window._param_value_spin.setValue(sigma)
            return

        self._window._param_value_spin.setDecimals(3)
        self._window._param_value_spin.setSingleStep(0.1)
        self._window._param_value_spin.setRange(-1000.0, 1000.0)
        self._window._param_value_spin.setValue(value)

    def on_apply_filter_param(self) -> None:
        step_index = self._window._get_selected_filter_step_index()
        param_key = self._window._param_key_combo.currentText().strip()
        if step_index < 0 or not param_key:
            return
        value = float(self._window._param_value_spin.value())
        if param_key == "window":
            window = self._normalize_window(value)
            value = window
            self._window._param_value_spin.setValue(float(window))
        elif param_key == "sigma":
            sigma = self._normalize_sigma(value)
            value = sigma
            self._window._param_value_spin.setValue(sigma)
        self._window._filter_pipeline.update_step_params(step_index, {param_key: value})
        self._window._status_label.setText(f"状态: 已更新步骤{step_index + 1}参数 {param_key}={value}")
        self.recompute_current_view_with_filters()

    def recompute_current_view_with_filters(self) -> None:
        if not self._window._last_raw_payload:
            return
        filtered, stage_curves = self.apply_pipeline_with_stages_safe(self._window._last_raw_payload)
        self._window._latest_payload = list(filtered)
        self._window._waveform_widget.update_curves(self._window._last_raw_payload, filtered, stage_curves)
        self._window._threshold_controller.refresh_with_payload(filtered)
        self._window._table_widget.update_data(filtered)

    def apply_pipeline_safe(self, raw_data: list[int]) -> list[int]:
        try:
            filtered = self._window._filter_pipeline.apply(raw_data)
            self._window._last_filter_error = ""
            return filtered
        except Exception as exc:
            message = str(exc)
            if message != self._window._last_filter_error:
                self._window._status_label.setText(f"状态: 滤波执行失败，已回退原始数据 ({message})")
                self._window._last_filter_error = message
            return list(raw_data)

    def apply_pipeline_with_stages_safe(self, raw_data: list[int]) -> tuple[list[int], list[tuple[str, list[int]]]]:
        try:
            stages = self._window._filter_pipeline.apply_with_stages(raw_data)
            if not stages:
                self._window._last_filter_error = ""
                return list(raw_data), []
            self._window._last_filter_error = ""
            final_data = list(stages[-1][1])
            return final_data, stages
        except Exception as exc:
            message = str(exc)
            if message != self._window._last_filter_error:
                self._window._status_label.setText(f"状态: 滤波执行失败，已回退原始数据 ({message})")
                self._window._last_filter_error = message
            return list(raw_data), []

    @staticmethod
    def _normalize_window(value: float) -> int:
        window = int(round(value))
        if window < 3:
            window = 3
        if window % 2 == 0:
            window += 1
        if window > 127:
            window = 127
        return window

    @staticmethod
    def _normalize_sigma(value: float) -> float:
        return max(0.1, min(20.0, float(value)))
