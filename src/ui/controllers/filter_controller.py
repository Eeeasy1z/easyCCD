from __future__ import annotations


class FilterController:
    def __init__(self, window) -> None:
        self._window = window

    def refresh_filter_step_ui(self) -> None:
        steps = self._window._filter_pipeline.get_steps()
        self._window._filter_step_combo.blockSignals(True)
        self._window._filter_step_combo.clear()
        for idx, step in enumerate(steps):
            self._window._filter_step_combo.addItem(f"{idx + 1}. {step.filter_name}")
        self._window._filter_step_combo.blockSignals(False)
        has_steps = bool(steps)
        self._window._remove_filter_button.setEnabled(has_steps)
        self._window._move_up_button.setEnabled(has_steps)
        self._window._move_down_button.setEnabled(has_steps)
        self._window._param_key_combo.setEnabled(has_steps)
        self._window._param_value_spin.setEnabled(has_steps)
        self._window._apply_param_button.setEnabled(has_steps)
        if has_steps:
            self._window._filter_step_combo.setCurrentIndex(0)
            self.on_filter_step_selected(0)
        else:
            self._window._param_key_combo.clear()

    def on_add_filter_step(self) -> None:
        filter_name = self._window._available_filter_combo.currentText().strip()
        if not filter_name:
            return
        self._window._filter_pipeline.add_step(filter_name)
        self.refresh_filter_step_ui()
        self.recompute_current_view_with_filters()

    def on_remove_filter_step(self) -> None:
        index = self._window._filter_step_combo.currentIndex()
        if index < 0:
            return
        self._window._filter_pipeline.remove_step(index)
        self.refresh_filter_step_ui()
        self.recompute_current_view_with_filters()

    def on_move_filter_step_up(self) -> None:
        index = self._window._filter_step_combo.currentIndex()
        if index <= 0:
            return
        self._window._filter_pipeline.move_up(index)
        self.refresh_filter_step_ui()
        self._window._filter_step_combo.setCurrentIndex(index - 1)
        self.recompute_current_view_with_filters()

    def on_move_filter_step_down(self) -> None:
        index = self._window._filter_step_combo.currentIndex()
        if index < 0:
            return
        self._window._filter_pipeline.move_down(index)
        self.refresh_filter_step_ui()
        self._window._filter_step_combo.setCurrentIndex(min(index + 1, self._window._filter_step_combo.count() - 1))
        self.recompute_current_view_with_filters()

    def on_filter_step_selected(self, index: int) -> None:
        steps = self._window._filter_pipeline.get_steps()
        if not (0 <= index < len(steps)):
            self._window._param_key_combo.clear()
            return
        step = steps[index]
        self._window._param_key_combo.blockSignals(True)
        self._window._param_key_combo.clear()
        keys = list(step.params.keys())
        self._window._param_key_combo.addItems(keys)
        self._window._param_key_combo.blockSignals(False)
        if keys:
            first_key = keys[0]
            self.configure_param_editor(first_key, float(step.params[first_key]))

    def on_filter_param_key_changed(self, key: str) -> None:
        index = self._window._filter_step_combo.currentIndex()
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
            window = int(round(value))
            if window < 3:
                window = 3
            if window % 2 == 0:
                window += 1
            if window > 127:
                window = 127
            self._window._param_value_spin.setValue(float(window))
            return

        if key == "sigma":
            self._window._param_value_spin.setDecimals(3)
            self._window._param_value_spin.setSingleStep(0.1)
            self._window._param_value_spin.setRange(0.1, 20.0)
            sigma = max(0.1, min(20.0, float(value)))
            self._window._param_value_spin.setValue(sigma)
            return

        self._window._param_value_spin.setDecimals(3)
        self._window._param_value_spin.setSingleStep(0.1)
        self._window._param_value_spin.setRange(-1000.0, 1000.0)
        self._window._param_value_spin.setValue(value)

    def on_apply_filter_param(self) -> None:
        step_index = self._window._filter_step_combo.currentIndex()
        param_key = self._window._param_key_combo.currentText().strip()
        if step_index < 0 or not param_key:
            return
        value = float(self._window._param_value_spin.value())
        if param_key == "window":
            window = int(round(value))
            if window < 3:
                window = 3
            if window % 2 == 0:
                window += 1
            if window > 127:
                window = 127
            value = window
            self._window._param_value_spin.setValue(float(window))
        elif param_key == "sigma":
            sigma = max(0.1, min(20.0, value))
            value = sigma
            self._window._param_value_spin.setValue(sigma)
        self._window._filter_pipeline.update_step_params(step_index, {param_key: value})
        self._window._status_label.setText(f"状态: 已更新步骤{step_index + 1}参数 {param_key}={value}")
        self.recompute_current_view_with_filters()

    def recompute_current_view_with_filters(self) -> None:
        if not self._window._last_raw_payload:
            return
        filtered = self.apply_pipeline_safe(self._window._last_raw_payload)
        self._window._latest_payload = list(filtered)
        self._window._waveform_widget.update_curves(self._window._last_raw_payload, filtered)
        self._window._binary_preview_widget.update_from_payload(filtered)
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
