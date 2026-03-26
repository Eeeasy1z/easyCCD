from __future__ import annotations

from datetime import datetime


class SerialController:
    def __init__(self, window) -> None:
        self._window = window
        self._port_fast_refresh_active = False

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

    def toggle_connection(self) -> None:
        if self._window._connected:
            self.disconnect_serial()
            return
        self.connect_serial()

    def connect_serial(self) -> None:
        port = self._window._port_combo.currentText().strip()
        if not port or port.startswith("<"):
            self._window._status_label.setText("状态: 无可用串口")
            return

        baudrate = int(self._window._baud_combo.currentText())
        try:
            self._window._serial_manager.open(port, baudrate)
            self._window._serial_manager.start_receiving()
        except Exception as exc:
            self._window._status_label.setText(f"状态: 连接失败 ({exc})")
            self._window._connected = False
            self._window._set_connect_indicator(False)
            return

        self._window._connected = True
        self._window._set_connect_indicator(True)
        self._window._status_label.setText(f"状态: 已连接 {port} @ {baudrate}")

    def disconnect_serial(self) -> None:
        self._window._recording_controller.handle_unsaved_recording_before_interrupt()
        self._window._serial_manager.close()
        self._window._connected = False
        self._window._set_connect_indicator(False)
        self._window._status_label.setText("状态: 未连接")

    def on_serial_payload(self, payload: list[int], frame_no: int, timestamp: float) -> None:
        self._window._bridge.data_received.emit(payload, frame_no, timestamp)

    def on_data_received(self, payload: list[int], frame_no: int, _timestamp: float) -> None:
        self._window._blink_connect_indicator()
        self._window._raw_stream_widget.append_frame(frame_no, payload, source="串口")
        self._window._last_raw_payload = list(payload)
        filtered_payload = self._window._filter_controller.apply_pipeline_safe(payload)
        self._window._latest_payload = list(payload)
        self._window._latest_frame_no = frame_no
        self._window._waveform_widget.update_curves(payload, filtered_payload)
        self._window._binary_preview_widget.update_from_payload(filtered_payload)
        self._window._table_widget.update_data(filtered_payload)
        self._window._frame_label.setText(f"帧号: {frame_no}")
        _, received_ok, bad_frames = self._window._serial_manager.get_stats()
        total_cached = len(self._window._recorded_frames) + sum(len(batch.frames) for batch in self._window._record_batches)
        self._window._stats_label.setText(f"统计: 接收{received_ok} | 坏帧{bad_frames} | 录制{total_cached}")

        if self._window._recording:
            normalized = [int(value) for value in filtered_payload[:128]]
            if len(normalized) < 128:
                normalized.extend([0] * (128 - len(normalized)))
            self._window._recorded_frames.append((frame_no, datetime.now().timestamp(), normalized))
            self._window._unsaved_recording = True
            self._window._status_label.setText(f"状态: 录制中，已缓存 {len(self._window._recorded_frames)} 帧")
            _, received_ok_after, bad_frames_after = self._window._serial_manager.get_stats()
            total_cached_after = len(self._window._recorded_frames) + sum(len(batch.frames) for batch in self._window._record_batches)
            self._window._stats_label.setText(f"统计: 接收{received_ok_after} | 坏帧{bad_frames_after} | 录制{total_cached_after}")
            self._window._recording_controller.update_record_runtime_label()
