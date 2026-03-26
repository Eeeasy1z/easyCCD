from __future__ import annotations

import csv
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox


class PlaybackController:
    def __init__(self, window) -> None:
        self._window = window

    def load_playback_csv(self) -> None:
        selected_path, _ = QFileDialog.getOpenFileName(
            self._window,
            "加载回放CSV",
            str(self._window._default_record_dir),
            "CSV 文件 (*.csv)",
        )
        if not selected_path:
            return

        path_obj = Path(selected_path)
        self._window._default_record_dir = path_obj.parent

        try:
            with path_obj.open("r", encoding="utf-8-sig", newline="") as csv_file:
                rows = list(csv.reader(csv_file))
        except OSError as exc:
            QMessageBox.critical(self._window, "加载失败", f"读取CSV失败: {exc}")
            return

        if not rows:
            QMessageBox.warning(self._window, "提示", "CSV为空，无法回放。")
            return

        header = rows[0]
        has_schema = len(header) >= 3 and header[0] == "schema_version"
        required_pixel_cols = 128

        parsed_frames: list[tuple[int, float, list[int]]] = []
        for raw in rows[1:]:
            if not raw:
                continue
            try:
                if has_schema:
                    schema_version = raw[0].strip() if len(raw) > 0 else ""
                    if schema_version == "v2":
                        if len(raw) < 132:
                            continue
                        frame_no = int(raw[2])
                        timestamp = float(raw[3])
                        pixel_start = 4
                    else:
                        if len(raw) < 131:
                            continue
                        frame_no = int(raw[1])
                        timestamp = float(raw[2])
                        pixel_start = 3
                else:
                    frame_no = int(raw[0])
                    timestamp = float(raw[1]) if len(raw) > 1 else 0.0
                    pixel_start = 2
                payload = [int(value) for value in raw[pixel_start : pixel_start + required_pixel_cols]]
            except (ValueError, IndexError):
                continue

            if len(payload) < required_pixel_cols:
                payload.extend([0] * (required_pixel_cols - len(payload)))
            parsed_frames.append((frame_no, timestamp, payload[:required_pixel_cols]))

        if not parsed_frames:
            QMessageBox.warning(self._window, "提示", "未解析到可回放的数据帧。")
            return

        self._window._playback_frames = parsed_frames
        self._window._playback_index = 0
        self._window._prev_frame_button.setEnabled(True)
        self._window._next_frame_button.setEnabled(True)
        self._window._play_pause_button.setEnabled(True)
        self._window._play_pause_button.setText("▶")
        self._window._playback_playing = False
        self._window._playback_timer.stop()
        self._window._playback_slider.setEnabled(True)
        self._window._playback_slider.blockSignals(True)
        self._window._playback_slider.setMaximum(len(parsed_frames) - 1)
        self._window._playback_slider.setValue(0)
        self._window._playback_slider.blockSignals(False)
        self.apply_playback_speed()
        self.show_playback_frame(self._window._playback_index)
        self._window._status_label.setText(f"状态: 已加载回放数据 {len(parsed_frames)} 帧")

    def show_playback_frame(self, index: int) -> None:
        if not self._window._playback_frames:
            return
        if index < 0 or index >= len(self._window._playback_frames):
            return

        frame_no, _timestamp, payload = self._window._playback_frames[index]
        filtered_payload = self._window._apply_pipeline_safe(payload)
        self._window._playback_index = index
        self._window._last_raw_payload = list(payload)
        self._window._latest_payload = list(filtered_payload)
        self._window._latest_frame_no = frame_no
        self._window._waveform_widget.update_curves(payload, filtered_payload)
        self._window._binary_preview_widget.update_from_payload(filtered_payload)
        self._window._table_widget.update_data(filtered_payload)
        self._window._raw_stream_widget.append_frame(frame_no, payload, source="回放")
        self._window._frame_label.setText(f"帧号: {frame_no} (回放 {index + 1}/{len(self._window._playback_frames)})")
        self._window._playback_slider.blockSignals(True)
        self._window._playback_slider.setValue(index)
        self._window._playback_slider.blockSignals(False)

    def show_prev_playback_frame(self) -> None:
        if not self._window._playback_frames:
            return
        if self._window._playback_playing:
            self.toggle_playback()
        next_index = self._window._playback_index - 1
        if next_index < 0:
            next_index = 0
        self.show_playback_frame(next_index)

    def show_next_playback_frame(self) -> None:
        if not self._window._playback_frames:
            return
        if self._window._playback_playing:
            self.toggle_playback()
        next_index = self._window._playback_index + 1
        if next_index >= len(self._window._playback_frames):
            next_index = len(self._window._playback_frames) - 1
        self.show_playback_frame(next_index)

    def apply_playback_speed(self) -> None:
        speed_text = self._window._speed_combo.currentText()
        interval_map = {"0.5x": 200, "1x": 100, "2x": 50}
        interval = interval_map.get(speed_text, 100)
        self._window._playback_timer.setInterval(interval)

    def toggle_playback(self) -> None:
        if not self._window._playback_frames:
            return
        if self._window._playback_playing:
            self._window._playback_playing = False
            self._window._playback_timer.stop()
            self._window._play_pause_button.setText("▶")
            return
        self._window._playback_playing = True
        self.apply_playback_speed()
        self._window._playback_timer.start()
        self._window._play_pause_button.setText("❚❚")

    def playback_tick(self) -> None:
        if not self._window._playback_frames:
            self._window._playback_timer.stop()
            self._window._playback_playing = False
            self._window._play_pause_button.setText("▶")
            return
        next_index = self._window._playback_index + 1
        if next_index >= len(self._window._playback_frames):
            self._window._playback_timer.stop()
            self._window._playback_playing = False
            self._window._play_pause_button.setText("▶")
            return
        self.show_playback_frame(next_index)

    def on_playback_slider_changed(self, value: int) -> None:
        if not self._window._playback_frames:
            return
        if self._window._playback_playing:
            self.toggle_playback()
        self.show_playback_frame(value)
