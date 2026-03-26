from __future__ import annotations

import csv
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox


@dataclass
class RecordingBatch:
    started_at: float
    ended_at: float
    frames: list[tuple[int, float, list[int]]]


class RecordingController:
    def __init__(self, window) -> None:
        self._window = window
        self._window._record_batches = []

    def choose_default_record_dir(self) -> None:
        selected_dir = QFileDialog.getExistingDirectory(
            self._window,
            "设置默认录制目录",
            str(self._window._default_record_dir),
        )
        if not selected_dir:
            return
        self._window._default_record_dir = Path(selected_dir)
        self._window._status_label.setText(f"状态: 默认目录已设置 {self._window._default_record_dir}")

    def reset_default_record_dir(self) -> None:
        self._window._default_record_dir = self._window._app_data_dir
        self._window._status_label.setText(f"状态: 默认目录已恢复 {self._window._default_record_dir}")

    def on_capacity_changed(self, value: int) -> None:
        self._window._record_capacity = int(value)
        old_frames = list(self._window._recorded_frames)
        self._window._recorded_frames = deque(old_frames[-self._window._record_capacity :], maxlen=self._window._record_capacity)
        self._window._stats_label.setText(
            self._window._stats_label.text().split("|")[0].strip()
            + f" | 坏帧{self._window._serial_manager.get_stats()[2]} | 录制{len(self._window._recorded_frames)}"
        )

    def build_auto_filename(self) -> str:
        return f"ccd_batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    def toggle_recording(self) -> None:
        if self._window._recording:
            self.stop_recording_and_store_batch()
            return

        self._window._recorded_frames.clear()
        self._window._recording = True
        self._window._unsaved_recording = False
        self._window._record_started_at = datetime.now().timestamp()
        self._window._set_record_button_state(True)
        self._window._status_label.setText("状态: 录制中，已缓存 0 帧")

    def stop_recording_and_store_batch(self) -> None:
        self._window._recording = False
        self._window._set_record_button_state(False)

        if not self._window._recorded_frames:
            QMessageBox.warning(self._window, "提示", "未录制到任何数据帧。")
            self._window._status_label.setText("状态: 录制结束（0帧）")
            self._window._record_runtime_label.setText("录制: 00:00 | FPS: 0.00")
            return

        ended_at = datetime.now().timestamp()
        batch = RecordingBatch(
            started_at=self._window._record_started_at or ended_at,
            ended_at=ended_at,
            frames=list(self._window._recorded_frames),
        )
        self._window._record_batches.append(batch)
        self._window._recorded_frames.clear()
        self._window._unsaved_recording = True
        self._window._record_started_at = None
        self._window._record_runtime_label.setText("录制: 00:00 | FPS: 0.00")
        self._window._status_label.setText(f"状态: 已暂存录制批次，当前共 {len(self._window._record_batches)} 批")

    def export_batches(self) -> None:
        if not self._window._record_batches:
            QMessageBox.information(self._window, "提示", "当前没有可导出的暂存批次。")
            return

        self._window._default_record_dir.mkdir(parents=True, exist_ok=True)
        base_name = self.build_auto_filename().replace(".csv", "")
        selected_path, _ = QFileDialog.getSaveFileName(
            self._window,
            "导出暂存录制数据",
            str(self._window._default_record_dir / f"{base_name}_all.csv"),
            "CSV 文件 (*.csv)",
        )
        if not selected_path:
            return

        target = Path(selected_path)
        if target.suffix.lower() != ".csv":
            target = target.with_suffix(".csv")
        target.parent.mkdir(parents=True, exist_ok=True)

        header = ["schema_version", "批次", "帧号", "时间戳"] + [f"像素{i}" for i in range(128)]
        try:
            with target.open("w", newline="", encoding="utf-8-sig") as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow(header)
                for batch_idx, batch in enumerate(self._window._record_batches, start=1):
                    for frame_no, timestamp, payload in batch.frames:
                        writer.writerow(["v2", batch_idx, frame_no, f"{timestamp:.6f}", *payload])
        except OSError as exc:
            QMessageBox.critical(self._window, "导出失败", f"导出失败: {exc}")
            return

        batch_count = len(self._window._record_batches)
        frame_count = sum(len(batch.frames) for batch in self._window._record_batches)
        self._window._record_batches.clear()
        self._window._unsaved_recording = False
        self._window._status_label.setText(f"状态: 已导出 {batch_count} 批，共 {frame_count} 帧")
        QMessageBox.information(self._window, "导出成功", f"已导出 {batch_count} 批（{frame_count} 帧）到:\n{target}")

    def calculate_record_metrics(self) -> tuple[float, float]:
        if self._window._record_started_at is None:
            return 0.0, 0.0
        duration_seconds = max(0.0, datetime.now().timestamp() - self._window._record_started_at)
        if duration_seconds <= 0:
            return duration_seconds, 0.0
        return duration_seconds, len(self._window._recorded_frames) / duration_seconds

    def update_record_runtime_label(self) -> None:
        duration_seconds, avg_fps = self.calculate_record_metrics()
        total_seconds = int(duration_seconds)
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        self._window._record_runtime_label.setText(f"录制: {minutes:02d}:{seconds:02d} | FPS: {avg_fps:.2f}")

    def handle_unsaved_recording_before_interrupt(self) -> None:
        has_live_frames = bool(self._window._recorded_frames)
        has_batches = bool(self._window._record_batches)
        if not self._window._unsaved_recording and not has_live_frames and not has_batches:
            return

        choice = QMessageBox.question(
            self._window,
            "未导出录制数据",
            "检测到未导出的录制数据，是否立即导出？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if choice == QMessageBox.StandardButton.Yes:
            if self._window._recording:
                self._window._recording = False
                self.stop_recording_and_store_batch()
            self.export_batches()
