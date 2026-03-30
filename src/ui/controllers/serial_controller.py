from __future__ import annotations

import threading
from datetime import datetime


class SerialController:
    def __init__(self, window) -> None:
        self._window = window
        self._port_fast_refresh_active = False
        self._connecting = False
        self._connect_attempt_id = 0
        self._disconnect_attempt_id = 0
        self._shutting_down = False

    def _set_connecting_ui(self, connecting: bool, status_text: str | None = None) -> None:
        self._connecting = connecting
        self._window.set_connect_button_enabled(not connecting)
        if status_text is not None:
            self._window.set_status_text(status_text)

    def _set_disconnected_ui(self, status_text: str = "状态: 未连接") -> None:
        self._window.set_connection_state(False, status_text)

    def _set_connected_ui(self, port: str, baudrate: int) -> None:
        self._window.set_connection_state(True, f"状态: 已连接 {port} @ {baudrate}")

    def prepare_shutdown(self) -> None:
        self._shutting_down = True

    def refresh_ports(self) -> None:
        ports = self._window._serial_manager.scan_ports()
        current = self._window._port_combo.currentText()

        old_ports = [self._window._port_combo.itemText(i) for i in range(self._window._port_combo.count())]
        next_ports = ports or ["<无可用串口>"]
        if old_ports == next_ports:
            return

        self._window._port_combo.blockSignals(True)
        self._window._port_combo.clear()
        if ports:
            self._window._port_combo.addItems(ports)
            if current in ports:
                self._window._port_combo.setCurrentText(current)
        else:
            self._window._port_combo.addItem("<无可用串口>")
        self._window._port_combo.blockSignals(False)

    def on_port_combo_popup(self) -> None:
        self.refresh_ports()
        self._port_fast_refresh_active = True
        self._window._port_fast_refresh_timer.start()

    def on_port_combo_hide(self) -> None:
        self._port_fast_refresh_active = False
        self._window._port_fast_refresh_timer.stop()

    def on_port_fast_tick(self) -> None:
        if not self._port_fast_refresh_active:
            self._window._port_fast_refresh_timer.stop()
            return
        self.refresh_ports()

    def on_port_slow_tick(self) -> None:
        self.refresh_ports()

    def on_connect_timeout(self) -> None:
        if not self._connecting:
            return
        self._set_connecting_ui(False)
        self._set_disconnected_ui("状态: 连接超时，请检查COM口或设备占用")

    def toggle_connection(self) -> None:
        if self._connecting:
            return
        if self._window._connected:
            self.disconnect_serial()
            return
        self.connect_serial()

    def connect_serial(self) -> None:
        if self._shutting_down:
            return
        port = self._window._port_combo.currentText().strip()
        if not port or port.startswith("<"):
            self._window.set_status_text("状态: 无可用串口")
            return

        baudrate = int(self._window._baud_combo.currentText())
        self._connect_attempt_id += 1
        attempt_id = self._connect_attempt_id
        self._set_connecting_ui(True, f"状态: 正在连接 {port} ...")
        self._window._connect_watchdog_timer.start()

        worker = threading.Thread(target=self._connect_worker, args=(port, baudrate, attempt_id), daemon=True)
        worker.start()

    def _connect_worker(self, port: str, baudrate: int, attempt_id: int) -> None:
        success = False
        message = ""
        try:
            self._window._serial_manager.open(port, baudrate)
            self._window._serial_manager.start_receiving()
            success = True
        except Exception as exc:
            message = str(exc)
        self._window._bridge.connect_result.emit(success, message, port, baudrate, attempt_id)

    def on_connect_result(self, success: bool, message: str, port: str, baudrate: int, attempt_id: int) -> None:
        if attempt_id != self._connect_attempt_id:
            if success:
                self._close_serial_async()
            return
        if self._shutting_down:
            if success:
                self._close_serial_async()
            return

        self._window._connect_watchdog_timer.stop()
        self._set_connecting_ui(False)

        if not success:
            self._set_disconnected_ui(f"状态: 连接失败 ({message})")
            return

        self._set_connected_ui(port, baudrate)

    def _close_serial_async(self, attempt_id: int | None = None) -> None:
        def closer() -> None:
            ok = True
            try:
                self._window._serial_manager.close()
            except Exception:
                ok = False
            if attempt_id is not None:
                self._window._bridge.disconnect_result.emit(ok, attempt_id)

        threading.Thread(target=closer, daemon=True).start()

    def disconnect_serial(self, async_mode: bool = True) -> None:
        self._set_disconnected_ui("状态: 未连接")
        self._set_connecting_ui(False)
        self._window._connect_watchdog_timer.stop()

        if async_mode and not self._shutting_down:
            self._disconnect_attempt_id += 1
            attempt_id = self._disconnect_attempt_id
            self._window.set_connect_button_enabled(False)
            self._close_serial_async(attempt_id)
            return

        try:
            self._window._serial_manager.close()
        finally:
            self._window.set_connect_button_enabled(True)

    def on_disconnect_result(self, success: bool, attempt_id: int) -> None:
        if attempt_id != self._disconnect_attempt_id:
            return
        if self._shutting_down:
            return
        self._window.set_connect_button_enabled(True)
        if not success:
            self._window.set_status_text("状态: 断开连接时出现异常，已尝试恢复")

    def on_serial_payload(self, payload: list[int], frame_no: int, timestamp: float) -> None:
        if self._shutting_down:
            return
        self._window._bridge.data_received.emit(payload, frame_no, timestamp)

    def on_data_received(self, payload: list[int], frame_no: int, _timestamp: float) -> None:
        if self._shutting_down:
            return
        self._window._blink_connect_indicator()
        self._window._raw_stream_widget.append_frame(frame_no, payload, source="串口")
        filtered_payload, stage_curves = self._window._filter_controller.apply_pipeline_with_stages_safe(payload)
        self._window.render_frame_views(payload, filtered_payload, frame_no)
        self._window._waveform_widget.update_curves(payload, filtered_payload, stage_curves)
        _, received_ok, bad_frames = self._window._serial_manager.get_stats()
        total_cached = len(self._window._recorded_frames) + sum(len(batch.frames) for batch in self._window._record_batches)
        self._window.set_stats_counts(received_ok, bad_frames, total_cached)

        if self._window._recording:
            normalized = [int(value) for value in filtered_payload[:128]]
            if len(normalized) < 128:
                normalized.extend([0] * (128 - len(normalized)))
            self._window._recorded_frames.append((frame_no, datetime.now().timestamp(), normalized))
            self._window._unsaved_recording = True
            self._window.set_status_text(f"状态: 录制中，已缓存 {len(self._window._recorded_frames)} 帧")
            _, received_ok_after, bad_frames_after = self._window._serial_manager.get_stats()
            total_cached_after = len(self._window._recorded_frames) + sum(len(batch.frames) for batch in self._window._record_batches)
            self._window.set_stats_counts(received_ok_after, bad_frames_after, total_cached_after)
            self._window._recording_controller.update_record_runtime_label()
