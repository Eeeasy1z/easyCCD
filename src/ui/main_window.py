from __future__ import annotations

import csv
import json
from datetime import datetime
from collections import deque
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QComboBox,
    QFileDialog,
    QSpinBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from comm.serial_manager import SerialManager
from core.filter_pipeline import FilterPipeline
from ui.widgets.data_table_widget import DataTableWidget
from ui.widgets.waveform_widget import WaveformWidget


class SerialSignalBridge(QObject):
    data_received = Signal(list, int, float)


class MainWindow(QMainWindow):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("EasyCCD MVP 上位机")
        self.resize(1200, 760)

        self._serial_manager = SerialManager()
        self._bridge = SerialSignalBridge()

        self._connected = False
        self._latest_payload: list[int] = []
        self._latest_frame_no = 0
        self._recording = False
        self._record_capacity = 5000
        self._recorded_frames: deque[tuple[int, float, list[int]]] = deque(maxlen=self._record_capacity)
        self._record_target_path: Path | None = None
        self._default_record_dir = Path.cwd()
        self._unsaved_recording = False
        self._name_template = "日期时间"
        self._record_started_at: float | None = None
        self._playback_frames: list[tuple[int, float, list[int]]] = []
        self._playback_index = -1
        self._playback_timer = QTimer(self)
        self._playback_timer.timeout.connect(self._playback_tick)
        self._playback_playing = False
        self._filter_pipeline = FilterPipeline()
        self._last_raw_payload: list[int] = []
        self._last_filter_error = ""

        self._build_ui()
        self._connect_signals()
        self._refresh_filter_step_ui()
        self.refresh_ports()
        self._apply_dark_theme()

    def _build_ui(self) -> None:
        root = QWidget(self)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(8)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        port_label = QLabel("串口:", self)
        self._port_combo = QComboBox(self)
        self._port_combo.setMinimumWidth(180)

        self._refresh_button = QPushButton("扫描串口", self)

        baud_label = QLabel("波特率:", self)
        self._baud_combo = QComboBox(self)
        self._baud_combo.addItems(["9600", "19200", "38400", "57600", "115200"])
        self._baud_combo.setCurrentText("115200")

        serial_group_label = QLabel("串口控制:", self)
        self._connect_button = QPushButton("连接", self)
        self._record_button = QPushButton("开始录制", self)
        self._path_button = QPushButton("设置保存路径", self)
        self._dir_button = QPushButton("设置默认目录", self)

        config_label = QLabel("录制配置:", self)
        self._capacity_spin = QSpinBox(self)
        self._capacity_spin.setRange(100, 200000)
        self._capacity_spin.setSingleStep(100)
        self._capacity_spin.setValue(self._record_capacity)
        self._capacity_spin.setSuffix(" 帧")

        self._name_template_combo = QComboBox(self)
        self._name_template_combo.addItems(["日期时间", "日期时间_串口_波特率"])
        self._name_template_combo.setCurrentText(self._name_template)
        self._load_csv_button = QPushButton("加载CSV", self)
        self._prev_frame_button = QPushButton("上一帧", self)
        self._next_frame_button = QPushButton("下一帧", self)
        self._play_pause_button = QPushButton("播放", self)
        self._speed_combo = QComboBox(self)
        self._speed_combo.addItems(["0.5x", "1x", "2x"])
        self._speed_combo.setCurrentText("1x")
        self._prev_frame_button.setEnabled(False)
        self._next_frame_button.setEnabled(False)
        self._play_pause_button.setEnabled(False)

        self._playback_slider = QSlider(Qt.Orientation.Horizontal, self)
        self._playback_slider.setMinimum(0)
        self._playback_slider.setMaximum(0)
        self._playback_slider.setValue(0)
        self._playback_slider.setEnabled(False)
        self._playback_slider.setFixedWidth(220)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        filter_row.addWidget(QLabel("滤波配置:", self))
        self._available_filter_combo = QComboBox(self)
        self._available_filter_combo.addItems(self._filter_pipeline.get_available_filters())
        self._add_filter_button = QPushButton("添加滤波器", self)
        self._filter_step_combo = QComboBox(self)
        self._remove_filter_button = QPushButton("删除步骤", self)
        self._move_up_button = QPushButton("上移", self)
        self._move_down_button = QPushButton("下移", self)
        self._param_key_combo = QComboBox(self)
        self._param_value_spin = QDoubleSpinBox(self)
        self._param_value_spin.setDecimals(3)
        self._param_value_spin.setRange(-1000.0, 1000.0)
        self._apply_param_button = QPushButton("应用参数", self)

        filter_row.addWidget(self._available_filter_combo)
        filter_row.addWidget(self._add_filter_button)
        filter_row.addSpacing(8)
        filter_row.addWidget(QLabel("当前链:", self))
        filter_row.addWidget(self._filter_step_combo)
        filter_row.addWidget(self._move_up_button)
        filter_row.addWidget(self._move_down_button)
        filter_row.addWidget(self._remove_filter_button)
        filter_row.addSpacing(8)
        filter_row.addWidget(QLabel("参数:", self))
        filter_row.addWidget(self._param_key_combo)
        filter_row.addWidget(self._param_value_spin)
        filter_row.addWidget(self._apply_param_button)
        filter_row.addStretch(1)

        top_row.addWidget(port_label)
        top_row.addWidget(self._port_combo)
        top_row.addWidget(self._refresh_button)
        top_row.addSpacing(12)
        top_row.addWidget(baud_label)
        top_row.addWidget(self._baud_combo)
        top_row.addSpacing(12)
        top_row.addWidget(serial_group_label)
        top_row.addWidget(self._connect_button)
        top_row.addSpacing(12)
        top_row.addWidget(config_label)
        top_row.addWidget(QLabel("缓存上限:", self))
        top_row.addWidget(self._capacity_spin)
        top_row.addWidget(QLabel("命名模板:", self))
        top_row.addWidget(self._name_template_combo)
        top_row.addWidget(self._dir_button)
        top_row.addStretch(1)
        top_row.addWidget(self._path_button)
        top_row.addWidget(self._record_button)
        top_row.addSpacing(12)
        top_row.addWidget(self._load_csv_button)
        top_row.addWidget(self._play_pause_button)
        top_row.addWidget(self._speed_combo)
        top_row.addWidget(self._prev_frame_button)
        top_row.addWidget(self._next_frame_button)
        top_row.addWidget(self._playback_slider)

        self._waveform_widget = WaveformWidget(self)
        self._table_widget = DataTableWidget(self)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(self._waveform_widget)
        splitter.addWidget(self._table_widget)
        splitter.setSizes([720, 440])

        root_layout.addLayout(top_row)
        root_layout.addLayout(filter_row)
        root_layout.addWidget(splitter, 1)

        self.setCentralWidget(root)

        status_bar = QStatusBar(self)
        self._status_label = QLabel("状态: 未连接", self)
        self._frame_label = QLabel("帧号: 0", self)
        self._stats_label = QLabel("统计: 接收0 | 坏帧0 | 录制0", self)
        self._record_runtime_label = QLabel("录制: 00:00 | FPS: 0.00", self)
        status_bar.addWidget(self._status_label)
        status_bar.addWidget(self._stats_label)
        status_bar.addWidget(self._record_runtime_label)
        status_bar.addPermanentWidget(self._frame_label)
        self.setStatusBar(status_bar)

    def _connect_signals(self) -> None:
        self._refresh_button.clicked.connect(self.refresh_ports)
        self._connect_button.clicked.connect(self._toggle_connection)
        self._path_button.clicked.connect(self._choose_record_path)
        self._dir_button.clicked.connect(self._choose_default_record_dir)
        self._record_button.clicked.connect(self._toggle_recording)
        self._capacity_spin.valueChanged.connect(self._on_capacity_changed)
        self._name_template_combo.currentTextChanged.connect(self._on_name_template_changed)
        self._load_csv_button.clicked.connect(self._load_playback_csv)
        self._prev_frame_button.clicked.connect(self._show_prev_playback_frame)
        self._next_frame_button.clicked.connect(self._show_next_playback_frame)
        self._play_pause_button.clicked.connect(self._toggle_playback)
        self._speed_combo.currentTextChanged.connect(self._apply_playback_speed)
        self._playback_slider.valueChanged.connect(self._on_playback_slider_changed)
        self._add_filter_button.clicked.connect(self._on_add_filter_step)
        self._remove_filter_button.clicked.connect(self._on_remove_filter_step)
        self._move_up_button.clicked.connect(self._on_move_filter_step_up)
        self._move_down_button.clicked.connect(self._on_move_filter_step_down)
        self._filter_step_combo.currentIndexChanged.connect(self._on_filter_step_selected)
        self._param_key_combo.currentTextChanged.connect(self._on_filter_param_key_changed)
        self._apply_param_button.clicked.connect(self._on_apply_filter_param)

        self._bridge.data_received.connect(self._on_data_received)
        self._serial_manager.register_callback(self._on_serial_payload)

    def _apply_dark_theme(self) -> None:
        self.setStyleSheet(
            "QMainWindow { background-color: #0F0F0F; }"
            "QLabel { color: #EAEAEA; }"
            "QComboBox, QPushButton { background-color: #1A1A1A; color: #EAEAEA; border: 1px solid #2A2A2A; border-radius: 4px; padding: 6px 8px; }"
            "QPushButton:hover { background-color: #242424; }"
            "QStatusBar { background-color: #141414; color: #D0D0D0; border-top: 1px solid #2A2A2A; }"
            "QSplitter::handle { background: #202020; }"
        )

    def refresh_ports(self) -> None:
        ports = self._serial_manager.scan_ports()
        current = self._port_combo.currentText()
        self._port_combo.blockSignals(True)
        self._port_combo.clear()
        if ports:
            self._port_combo.addItems(ports)
            if current in ports:
                self._port_combo.setCurrentText(current)
        else:
            self._port_combo.addItem("<无可用串口>")
        self._port_combo.blockSignals(False)

    def _toggle_connection(self) -> None:
        if self._connected:
            self._disconnect_serial()
            return
        self._connect_serial()

    def _connect_serial(self) -> None:
        port = self._port_combo.currentText().strip()
        if not port or port.startswith("<"):
            self._status_label.setText("状态: 无可用串口")
            return

        baudrate = int(self._baud_combo.currentText())
        try:
            self._serial_manager.open(port, baudrate)
            self._serial_manager.start_receiving()
        except Exception as exc:
            self._status_label.setText(f"状态: 连接失败 ({exc})")
            self._connect_button.setText("连接")
            self._connected = False
            return

        self._connected = True
        self._connect_button.setText("断开")
        self._status_label.setText(f"状态: 已连接 {port} @ {baudrate}")

    def _disconnect_serial(self) -> None:
        self._handle_unsaved_recording_before_interrupt()
        self._serial_manager.close()
        self._connected = False
        self._connect_button.setText("连接")
        self._status_label.setText("状态: 未连接")

    def _on_serial_payload(self, payload: list[int], frame_no: int, timestamp: float) -> None:
        self._bridge.data_received.emit(payload, frame_no, timestamp)

    def _on_data_received(self, payload: list[int], frame_no: int, _timestamp: float) -> None:
        self._last_raw_payload = list(payload)
        filtered_payload = self._apply_pipeline_safe(payload)
        self._latest_payload = list(payload)
        self._latest_frame_no = frame_no
        self._waveform_widget.update_curves(payload, filtered_payload)
        self._table_widget.update_data(filtered_payload)
        self._frame_label.setText(f"帧号: {frame_no}")
        _, received_ok, bad_frames = self._serial_manager.get_stats()
        self._stats_label.setText(f"统计: 接收{received_ok} | 坏帧{bad_frames} | 录制{len(self._recorded_frames)}")

        if self._recording:
            normalized = [int(value) for value in filtered_payload[:128]]
            if len(normalized) < 128:
                normalized.extend([0] * (128 - len(normalized)))
            self._recorded_frames.append((frame_no, datetime.now().timestamp(), normalized))
            self._unsaved_recording = True
            self._status_label.setText(f"状态: 录制中，已缓存 {len(self._recorded_frames)} 帧")
            _, received_ok_after, bad_frames_after = self._serial_manager.get_stats()
            self._stats_label.setText(f"统计: 接收{received_ok_after} | 坏帧{bad_frames_after} | 录制{len(self._recorded_frames)}")
            self._update_record_runtime_label()

    def _choose_record_path(self) -> bool:
        default_name = self._build_auto_filename()
        selected_path, _ = QFileDialog.getSaveFileName(
            self,
            "设置批量录制导出路径",
            str(self._default_record_dir / default_name),
            "CSV 文件 (*.csv)",
        )
        if not selected_path:
            return False

        path_obj = Path(selected_path)
        if path_obj.suffix.lower() != ".csv":
            path_obj = path_obj.with_suffix(".csv")

        self._record_target_path = path_obj
        self._default_record_dir = path_obj.parent
        self._status_label.setText(f"状态: 已设置保存路径 {path_obj.name}")
        return True

    def _choose_default_record_dir(self) -> None:
        selected_dir = QFileDialog.getExistingDirectory(self, "设置默认录制目录", str(self._default_record_dir))
        if not selected_dir:
            return
        self._default_record_dir = Path(selected_dir)
        self._status_label.setText(f"状态: 默认目录已设置 {self._default_record_dir}")
        if self._record_target_path is not None:
            self._record_target_path = self._default_record_dir / self._record_target_path.name

    def _on_capacity_changed(self, value: int) -> None:
        self._record_capacity = int(value)
        old_frames = list(self._recorded_frames)
        self._recorded_frames = deque(old_frames[-self._record_capacity :], maxlen=self._record_capacity)
        self._stats_label.setText(self._stats_label.text().split("|")[0].strip() + f" | 坏帧{self._serial_manager.get_stats()[2]} | 录制{len(self._recorded_frames)}")

    def _on_name_template_changed(self, value: str) -> None:
        self._name_template = value
        self._status_label.setText(f"状态: 命名模板已切换为 {value}")

    def _build_auto_filename(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if self._name_template == "日期时间_串口_波特率":
            port = self._port_combo.currentText().strip() or "COMX"
            baud = self._baud_combo.currentText().strip() or "115200"
            safe_port = port.replace(" ", "_").replace("/", "_").replace("\\", "_")
            return f"ccd_batch_{timestamp}_{safe_port}_{baud}.csv"
        return f"ccd_batch_{timestamp}.csv"

    def _toggle_recording(self) -> None:
        if self._recording:
            self._stop_recording_and_export()
            return

        if self._record_target_path is None and not self._choose_record_path():
            QMessageBox.warning(self, "提示", "请先设置CSV保存路径后再开始录制。")
            return

        if self._record_target_path is not None:
            self._record_target_path = self._default_record_dir / self._build_auto_filename()

        self._recorded_frames.clear()
        self._recording = True
        self._unsaved_recording = False
        self._record_started_at = datetime.now().timestamp()
        self._record_button.setText("结束录制")
        self._record_button.setStyleSheet("background-color: #C62828; color: #FFFFFF; border: 1px solid #8E0000; border-radius: 4px; padding: 6px 8px;")
        self._status_label.setText("状态: 录制中，已缓存 0 帧")

    def _stop_recording_and_export(self) -> None:
        self._recording = False
        self._record_button.setText("开始录制")
        self._record_button.setStyleSheet("")

        if self._record_target_path is None:
            self._status_label.setText("状态: 未连接")
            return

        if not self._recorded_frames:
            QMessageBox.warning(self, "提示", "未录制到任何数据帧。")
            self._status_label.setText("状态: 录制结束（0帧）")
            self._record_runtime_label.setText("录制: 00:00 | FPS: 0.00")
            return

        header = ["schema_version", "帧号", "时间戳"] + [f"像素{i}" for i in range(128)]
        try:
            with self._record_target_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow(header)
                for frame_no, timestamp, payload in self._recorded_frames:
                    writer.writerow(["v1", frame_no, f"{timestamp:.6f}", *payload])
        except OSError as exc:
            QMessageBox.critical(self, "导出失败", f"批量导出失败: {exc}")
            return

        exported_count = len(self._recorded_frames)
        exported_path = self._record_target_path
        runtime_seconds, avg_fps = self._calculate_record_metrics()

        summary_path = exported_path.with_name(f"{exported_path.stem}_summary.json")
        callback_frames, received_ok, bad_frames = self._serial_manager.get_stats()
        summary_data = {
            "schema_version": "summary_v1",
            "csv_schema_version": "v1",
            "record_file": str(exported_path),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "port": self._port_combo.currentText(),
            "baudrate": int(self._baud_combo.currentText()),
            "recorded_frames": exported_count,
            "received_valid_frames": received_ok,
            "callback_frames": callback_frames,
            "bad_frames": bad_frames,
            "duration_seconds": round(runtime_seconds, 3),
            "avg_fps": round(avg_fps, 3),
            "record_capacity": self._record_capacity,
            "file_name_template": self._name_template,
        }
        try:
            with summary_path.open("w", encoding="utf-8") as json_file:
                json.dump(summary_data, json_file, ensure_ascii=False, indent=2)
        except OSError:
            pass

        self._recorded_frames.clear()
        self._unsaved_recording = False
        self._record_started_at = None
        self._record_runtime_label.setText("录制: 00:00 | FPS: 0.00")
        self._status_label.setText(f"状态: 录制结束（{exported_count}帧）")
        QMessageBox.information(self, "导出成功", f"已导出 {exported_count} 帧到:\n{exported_path}\n会话摘要: {summary_path.name}")

    def _calculate_record_metrics(self) -> tuple[float, float]:
        if self._record_started_at is None:
            return 0.0, 0.0
        duration_seconds = max(0.0, datetime.now().timestamp() - self._record_started_at)
        if duration_seconds <= 0:
            return duration_seconds, 0.0
        return duration_seconds, len(self._recorded_frames) / duration_seconds

    def _update_record_runtime_label(self) -> None:
        duration_seconds, avg_fps = self._calculate_record_metrics()
        total_seconds = int(duration_seconds)
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        self._record_runtime_label.setText(f"录制: {minutes:02d}:{seconds:02d} | FPS: {avg_fps:.2f}")

    def _handle_unsaved_recording_before_interrupt(self) -> None:
        if not self._unsaved_recording or not self._recorded_frames:
            return
        choice = QMessageBox.question(
            self,
            "未导出录制数据",
            "检测到未导出的录制数据，是否立即导出？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if choice == QMessageBox.StandardButton.Yes:
            if self._recording:
                self._recording = False
            self._stop_recording_and_export()

    def _load_playback_csv(self) -> None:
        selected_path, _ = QFileDialog.getOpenFileName(
            self,
            "加载回放CSV",
            str(self._default_record_dir),
            "CSV 文件 (*.csv)",
        )
        if not selected_path:
            return

        path_obj = Path(selected_path)
        self._default_record_dir = path_obj.parent

        try:
            with path_obj.open("r", encoding="utf-8-sig", newline="") as csv_file:
                rows = list(csv.reader(csv_file))
        except OSError as exc:
            QMessageBox.critical(self, "加载失败", f"读取CSV失败: {exc}")
            return

        if not rows:
            QMessageBox.warning(self, "提示", "CSV为空，无法回放。")
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
            QMessageBox.warning(self, "提示", "未解析到可回放的数据帧。")
            return

        self._playback_frames = parsed_frames
        self._playback_index = 0
        self._prev_frame_button.setEnabled(True)
        self._next_frame_button.setEnabled(True)
        self._play_pause_button.setEnabled(True)
        self._play_pause_button.setText("播放")
        self._playback_playing = False
        self._playback_timer.stop()
        self._playback_slider.setEnabled(True)
        self._playback_slider.blockSignals(True)
        self._playback_slider.setMaximum(len(parsed_frames) - 1)
        self._playback_slider.setValue(0)
        self._playback_slider.blockSignals(False)
        self._apply_playback_speed()
        self._show_playback_frame(self._playback_index)
        self._status_label.setText(f"状态: 已加载回放数据 {len(parsed_frames)} 帧")

    def _show_playback_frame(self, index: int) -> None:
        if not self._playback_frames:
            return
        if index < 0 or index >= len(self._playback_frames):
            return

        frame_no, _timestamp, payload = self._playback_frames[index]
        filtered_payload = self._apply_pipeline_safe(payload)
        self._playback_index = index
        self._last_raw_payload = list(payload)
        self._latest_payload = list(filtered_payload)
        self._latest_frame_no = frame_no
        self._waveform_widget.update_curves(payload, filtered_payload)
        self._table_widget.update_data(filtered_payload)
        self._frame_label.setText(f"帧号: {frame_no} (回放 {index + 1}/{len(self._playback_frames)})")
        self._playback_slider.blockSignals(True)
        self._playback_slider.setValue(index)
        self._playback_slider.blockSignals(False)

    def _show_prev_playback_frame(self) -> None:
        if not self._playback_frames:
            return
        if self._playback_playing:
            self._toggle_playback()
        next_index = self._playback_index - 1
        if next_index < 0:
            next_index = 0
        self._show_playback_frame(next_index)

    def _show_next_playback_frame(self) -> None:
        if not self._playback_frames:
            return
        if self._playback_playing:
            self._toggle_playback()
        next_index = self._playback_index + 1
        if next_index >= len(self._playback_frames):
            next_index = len(self._playback_frames) - 1
        self._show_playback_frame(next_index)

    def _apply_playback_speed(self) -> None:
        speed_text = self._speed_combo.currentText()
        interval_map = {"0.5x": 200, "1x": 100, "2x": 50}
        interval = interval_map.get(speed_text, 100)
        self._playback_timer.setInterval(interval)

    def _toggle_playback(self) -> None:
        if not self._playback_frames:
            return
        if self._playback_playing:
            self._playback_playing = False
            self._playback_timer.stop()
            self._play_pause_button.setText("播放")
            return
        self._playback_playing = True
        self._apply_playback_speed()
        self._playback_timer.start()
        self._play_pause_button.setText("暂停")

    def _playback_tick(self) -> None:
        if not self._playback_frames:
            self._playback_timer.stop()
            self._playback_playing = False
            self._play_pause_button.setText("播放")
            return
        next_index = self._playback_index + 1
        if next_index >= len(self._playback_frames):
            self._playback_timer.stop()
            self._playback_playing = False
            self._play_pause_button.setText("播放")
            return
        self._show_playback_frame(next_index)

    def _on_playback_slider_changed(self, value: int) -> None:
        if not self._playback_frames:
            return
        if self._playback_playing:
            self._toggle_playback()
        self._show_playback_frame(value)

    def _refresh_filter_step_ui(self) -> None:
        steps = self._filter_pipeline.get_steps()
        self._filter_step_combo.blockSignals(True)
        self._filter_step_combo.clear()
        for idx, step in enumerate(steps):
            self._filter_step_combo.addItem(f"{idx + 1}. {step.filter_name}")
        self._filter_step_combo.blockSignals(False)
        has_steps = bool(steps)
        self._remove_filter_button.setEnabled(has_steps)
        self._move_up_button.setEnabled(has_steps)
        self._move_down_button.setEnabled(has_steps)
        self._param_key_combo.setEnabled(has_steps)
        self._param_value_spin.setEnabled(has_steps)
        self._apply_param_button.setEnabled(has_steps)
        if has_steps:
            self._filter_step_combo.setCurrentIndex(0)
            self._on_filter_step_selected(0)
        else:
            self._param_key_combo.clear()

    def _on_add_filter_step(self) -> None:
        filter_name = self._available_filter_combo.currentText().strip()
        if not filter_name:
            return
        self._filter_pipeline.add_step(filter_name)
        self._refresh_filter_step_ui()
        self._recompute_current_view_with_filters()

    def _on_remove_filter_step(self) -> None:
        index = self._filter_step_combo.currentIndex()
        if index < 0:
            return
        self._filter_pipeline.remove_step(index)
        self._refresh_filter_step_ui()
        self._recompute_current_view_with_filters()

    def _on_move_filter_step_up(self) -> None:
        index = self._filter_step_combo.currentIndex()
        if index <= 0:
            return
        self._filter_pipeline.move_up(index)
        self._refresh_filter_step_ui()
        self._filter_step_combo.setCurrentIndex(index - 1)
        self._recompute_current_view_with_filters()

    def _on_move_filter_step_down(self) -> None:
        index = self._filter_step_combo.currentIndex()
        if index < 0:
            return
        self._filter_pipeline.move_down(index)
        self._refresh_filter_step_ui()
        self._filter_step_combo.setCurrentIndex(min(index + 1, self._filter_step_combo.count() - 1))
        self._recompute_current_view_with_filters()

    def _on_filter_step_selected(self, index: int) -> None:
        steps = self._filter_pipeline.get_steps()
        if not (0 <= index < len(steps)):
            self._param_key_combo.clear()
            return
        step = steps[index]
        self._param_key_combo.blockSignals(True)
        self._param_key_combo.clear()
        keys = list(step.params.keys())
        self._param_key_combo.addItems(keys)
        self._param_key_combo.blockSignals(False)
        if keys:
            first_key = keys[0]
            self._configure_param_editor(first_key, float(step.params[first_key]))

    def _on_filter_param_key_changed(self, key: str) -> None:
        index = self._filter_step_combo.currentIndex()
        steps = self._filter_pipeline.get_steps()
        if not (0 <= index < len(steps)):
            return
        if key not in steps[index].params:
            return
        self._configure_param_editor(key, float(steps[index].params[key]))

    def _configure_param_editor(self, key: str, value: float) -> None:
        if key == "window":
            self._param_value_spin.setDecimals(0)
            self._param_value_spin.setSingleStep(2.0)
            self._param_value_spin.setRange(3.0, 127.0)
            window = int(round(value))
            if window < 3:
                window = 3
            if window % 2 == 0:
                window += 1
            if window > 127:
                window = 127
            self._param_value_spin.setValue(float(window))
            return

        if key == "sigma":
            self._param_value_spin.setDecimals(3)
            self._param_value_spin.setSingleStep(0.1)
            self._param_value_spin.setRange(0.1, 20.0)
            sigma = max(0.1, min(20.0, float(value)))
            self._param_value_spin.setValue(sigma)
            return

        self._param_value_spin.setDecimals(3)
        self._param_value_spin.setSingleStep(0.1)
        self._param_value_spin.setRange(-1000.0, 1000.0)
        self._param_value_spin.setValue(value)

    def _on_apply_filter_param(self) -> None:
        step_index = self._filter_step_combo.currentIndex()
        param_key = self._param_key_combo.currentText().strip()
        if step_index < 0 or not param_key:
            return
        value = float(self._param_value_spin.value())
        if param_key == "window":
            window = int(round(value))
            if window < 3:
                window = 3
            if window % 2 == 0:
                window += 1
            if window > 127:
                window = 127
            value = window
            self._param_value_spin.setValue(float(window))
        elif param_key == "sigma":
            sigma = max(0.1, min(20.0, value))
            value = sigma
            self._param_value_spin.setValue(sigma)
        self._filter_pipeline.update_step_params(step_index, {param_key: value})
        self._status_label.setText(f"状态: 已更新步骤{step_index + 1}参数 {param_key}={value}")
        self._recompute_current_view_with_filters()

    def _recompute_current_view_with_filters(self) -> None:
        if not self._last_raw_payload:
            return
        filtered = self._apply_pipeline_safe(self._last_raw_payload)
        self._latest_payload = list(filtered)
        self._waveform_widget.update_curves(self._last_raw_payload, filtered)
        self._table_widget.update_data(filtered)

    def _apply_pipeline_safe(self, raw_data: list[int]) -> list[int]:
        try:
            filtered = self._filter_pipeline.apply(raw_data)
            self._last_filter_error = ""
            return filtered
        except Exception as exc:
            message = str(exc)
            if message != self._last_filter_error:
                self._status_label.setText(f"状态: 滤波执行失败，已回退原始数据 ({message})")
                self._last_filter_error = message
            return list(raw_data)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._handle_unsaved_recording_before_interrupt()
        self._serial_manager.close()
        super().closeEvent(event)
