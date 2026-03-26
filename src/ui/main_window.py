from __future__ import annotations

from collections import deque
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QFontMetrics
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from comm.serial_manager import SerialManager
from core.filter_pipeline import FilterPipeline
from ui.controllers import FilterController, PlaybackController, RecordingController, SerialController
from ui.widgets.binary_preview_widget import BinaryPreviewWidget
from ui.widgets.data_table_widget import DataTableWidget
from ui.widgets.raw_stream_widget import RawStreamWidget
from ui.widgets.waveform_widget import WaveformWidget


class AutoRefreshPortComboBox(QComboBox):
    popup_opened = Signal()
    popup_closed = Signal()

    def showPopup(self) -> None:  # type: ignore[override]
        self.popup_opened.emit()
        super().showPopup()

    def hidePopup(self) -> None:  # type: ignore[override]
        super().hidePopup()
        self.popup_closed.emit()


class NoWheelComboBox(QComboBox):
    def wheelEvent(self, event) -> None:  # type: ignore[override]
        event.ignore()


class SerialSignalBridge(QObject):
    data_received = Signal(list, int, float)


class MainWindow(QMainWindow):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("EasyCCD 上位机")
        self.resize(1360, 820)

        self._serial_manager = SerialManager()
        self._bridge = SerialSignalBridge()
        self._app_data_dir = Path.cwd() / "数据保存"
        self._app_data_dir.mkdir(parents=True, exist_ok=True)

        self._connected = False
        self._latest_payload: list[int] = []
        self._latest_frame_no = 0
        self._recording = False
        self._record_capacity = 5000
        self._recorded_frames: deque[tuple[int, float, list[int]]] = deque(maxlen=self._record_capacity)
        self._default_record_dir = self._app_data_dir
        self._unsaved_recording = False
        self._record_started_at: float | None = None
        self._record_batches: list = []
        self._playback_frames: list[tuple[int, float, list[int]]] = []
        self._playback_index = -1
        self._playback_timer = QTimer(self)
        self._playback_playing = False
        self._filter_pipeline = FilterPipeline()
        self._last_raw_payload: list[int] = []
        self._last_filter_error = ""

        self._recording_controller = RecordingController(self)
        self._playback_controller = PlaybackController(self)
        self._filter_controller = FilterController(self)
        self._serial_controller = SerialController(self)

        self._playback_timer.timeout.connect(self._playback_tick)
        self._port_fast_refresh_timer = QTimer(self)
        self._port_fast_refresh_timer.setInterval(500)
        self._port_fast_refresh_timer.timeout.connect(self._serial_controller.on_port_fast_tick)
        self._port_slow_refresh_timer = QTimer(self)
        self._port_slow_refresh_timer.setInterval(10000)
        self._port_slow_refresh_timer.timeout.connect(self._serial_controller.on_port_slow_tick)

        self._build_menu_bar()
        self._build_ui()
        self._connect_signals()
        self._refresh_filter_step_ui()
        self.refresh_ports()
        self._port_slow_refresh_timer.start()
        self._apply_dark_theme()

    def _build_menu_bar(self) -> None:
        menu_bar = self.menuBar()

        self._file_menu = menu_bar.addMenu("文件")
        self._file_import_csv_action = QAction("导入CSV", self)
        self._file_export_data_action = QAction("导出数据", self)
        self._file_export_data_action.setEnabled(False)
        self._file_exit_action = QAction("退出", self)
        self._file_menu.addAction(self._file_import_csv_action)
        self._file_menu.addAction(self._file_export_data_action)
        self._file_menu.addSeparator()
        self._file_menu.addAction(self._file_exit_action)

        self._tools_menu = menu_bar.addMenu("工具")
        self._tools_toggle_filter_action = QAction("显示/隐藏滤波面板", self)
        self._tools_clear_filter_action = QAction("清空滤波链", self)
        self._tools_menu.addAction(self._tools_toggle_filter_action)
        self._tools_menu.addAction(self._tools_clear_filter_action)

        self._settings_menu = menu_bar.addMenu("设置")
        self._settings_choose_dir_action = QAction("设置保存目录", self)
        self._settings_reset_dir_action = QAction("恢复默认保存目录", self)
        self._settings_menu.addAction(self._settings_choose_dir_action)
        self._settings_menu.addAction(self._settings_reset_dir_action)

        self._help_menu = menu_bar.addMenu("帮助")
        self._help_protocol_action = QAction("协议说明", self)
        self._help_about_action = QAction("关于", self)
        self._help_menu.addAction(self._help_protocol_action)
        self._help_menu.addAction(self._help_about_action)

        self._adjust_menu_popup_width(self._file_menu)
        self._adjust_menu_popup_width(self._tools_menu)
        self._adjust_menu_popup_width(self._settings_menu)
        self._adjust_menu_popup_width(self._help_menu)

    def _adjust_menu_popup_width(self, menu) -> None:
        metrics = QFontMetrics(menu.font())
        min_width = 120
        for action in menu.actions():
            text = action.text().replace("&", "")
            if text:
                min_width = max(min_width, metrics.horizontalAdvance(text) + 56)
        menu.setMinimumWidth(min_width)

    def _build_ui(self) -> None:
        root = QWidget(self)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(8)

        top_controls_row = QHBoxLayout()
        top_controls_row.setSpacing(8)

        self._connect_button = QPushButton("", self)
        self._connect_button.setFixedSize(20, 20)
        self._connect_button.setToolTip("串口连接/断开")
        top_controls_row.addWidget(self._connect_button)

        top_controls_row.addWidget(QLabel("COM口:", self))
        self._port_combo = AutoRefreshPortComboBox(self)
        self._port_combo.setMinimumWidth(150)
        top_controls_row.addWidget(self._port_combo)

        top_controls_row.addWidget(QLabel("波特率:", self))
        self._baud_combo = QComboBox(self)
        self._baud_combo.addItems(["9600", "19200", "38400", "57600", "115200"])
        self._baud_combo.setCurrentText("115200")
        top_controls_row.addWidget(self._baud_combo)

        top_controls_row.addSpacing(14)
        divider = QFrame(self)
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setFrameShadow(QFrame.Shadow.Plain)
        divider.setStyleSheet("color: #3A3A3A;")
        top_controls_row.addWidget(divider)
        top_controls_row.addSpacing(14)

        self._record_button = QPushButton(self)
        self._record_button.setFixedHeight(30)
        top_controls_row.addWidget(self._record_button)

        top_controls_row.addSpacing(6)
        top_controls_row.addWidget(QLabel("回放:", self))
        self._prev_frame_button = QPushButton("上一帧", self)
        self._next_frame_button = QPushButton("下一帧", self)
        self._play_pause_button = QPushButton("▶", self)
        self._play_pause_button.setFixedSize(44, 32)
        self._play_pause_button.setStyleSheet("font-size: 18px; font-weight: 700;")
        self._play_pause_button.setToolTip("播放/暂停")
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
        self._playback_slider.setFixedWidth(260)

        top_controls_row.addWidget(self._play_pause_button)
        top_controls_row.addWidget(self._playback_slider)
        top_controls_row.addWidget(self._speed_combo)
        top_controls_row.addWidget(self._prev_frame_button)
        top_controls_row.addWidget(self._next_frame_button)
        top_controls_row.addStretch(1)

        self._capacity_spin = QSpinBox(self)
        self._capacity_spin.setRange(100, 200000)
        self._capacity_spin.setSingleStep(100)
        self._capacity_spin.setValue(self._record_capacity)
        self._capacity_spin.setSuffix(" 帧")

        self._filter_panel = QWidget(self)
        filter_panel_layout = QVBoxLayout(self._filter_panel)
        filter_panel_layout.setContentsMargins(0, 0, 0, 0)
        filter_panel_layout.setSpacing(6)

        filter_title = QLabel("滤波配置", self)
        filter_title.setStyleSheet("padding-left: 4px;")
        filter_panel_layout.addWidget(filter_title)

        available_title = QLabel("可用滤波器:", self)
        available_title.setStyleSheet("padding-left: 4px;")
        filter_panel_layout.addWidget(available_title)
        self._available_filter_combo = NoWheelComboBox(self)
        self._available_filter_combo.addItems(self._filter_pipeline.get_available_filters())
        filter_panel_layout.addWidget(self._available_filter_combo)

        self._add_filter_button = QPushButton("添加滤波器", self)
        filter_panel_layout.addWidget(self._add_filter_button)

        chain_title = QLabel("当前链:", self)
        chain_title.setStyleSheet("padding-left: 4px;")
        filter_panel_layout.addWidget(chain_title)
        self._filter_step_combo = NoWheelComboBox(self)
        filter_panel_layout.addWidget(self._filter_step_combo)

        self._remove_filter_button = QPushButton("删除步骤", self)
        filter_panel_layout.addWidget(self._remove_filter_button)

        self._move_up_button = QPushButton("上移", self)
        filter_panel_layout.addWidget(self._move_up_button)

        self._move_down_button = QPushButton("下移", self)
        filter_panel_layout.addWidget(self._move_down_button)

        param_key_title = QLabel("参数项:", self)
        param_key_title.setStyleSheet("padding-left: 4px;")
        filter_panel_layout.addWidget(param_key_title)
        self._param_key_combo = NoWheelComboBox(self)
        filter_panel_layout.addWidget(self._param_key_combo)

        param_value_title = QLabel("参数值:", self)
        param_value_title.setStyleSheet("padding-left: 4px;")
        filter_panel_layout.addWidget(param_value_title)
        self._param_value_spin = QDoubleSpinBox(self)
        self._param_value_spin.setDecimals(3)
        self._param_value_spin.setRange(-1000.0, 1000.0)
        filter_panel_layout.addWidget(self._param_value_spin)

        self._apply_param_button = QPushButton("应用参数", self)
        filter_panel_layout.addWidget(self._apply_param_button)
        filter_panel_layout.addStretch(1)

        self._waveform_widget = WaveformWidget(self)
        self._binary_preview_widget = BinaryPreviewWidget(self)
        left_splitter = QSplitter(Qt.Orientation.Vertical, self)
        left_splitter.addWidget(self._waveform_widget)
        left_splitter.addWidget(self._binary_preview_widget)
        left_splitter.setSizes([560, 170])

        self._table_widget = DataTableWidget(self)
        self._raw_stream_widget = RawStreamWidget(self)

        self._side_panel = QWidget(self)
        self._side_panel.setFixedWidth(220)
        side_layout = QVBoxLayout(self._side_panel)
        side_layout.setContentsMargins(8, 10, 8, 0)
        side_layout.setSpacing(8)
        cache_title = QLabel("缓存上限:", self)
        cache_title.setStyleSheet("padding-left: 4px;")
        side_layout.addWidget(cache_title)
        side_layout.addWidget(self._capacity_spin)
        side_layout.addWidget(self._filter_panel)
        side_layout.addStretch(1)

        self._settings_scroll = QScrollArea(self)
        self._settings_scroll.setWidgetResizable(True)
        self._settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._settings_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._settings_scroll.setFrameShape(QFrame.Shape.StyledPanel)
        self._settings_scroll.setStyleSheet(
            "QScrollArea { background-color: #0F0F0F; border: 1px solid #2A2A2A; }"
            "QScrollBar:vertical { background: transparent; width: 0px; margin: 0; }"
            "QScrollBar::handle:vertical { background: transparent; min-height: 0px; border: none; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
        )
        self._settings_scroll.viewport().setStyleSheet("background-color: #0F0F0F;")
        self._side_panel.setStyleSheet("background-color: #0F0F0F;")
        self._filter_panel.setStyleSheet("background-color: #0F0F0F;")
        self._settings_scroll.setWidget(self._side_panel)
        self._settings_scroll.setFixedWidth(220)

        right_top = QWidget(self)
        right_top_layout = QHBoxLayout(right_top)
        right_top_layout.setContentsMargins(0, 0, 0, 0)
        right_top_layout.setSpacing(8)
        right_top_layout.addWidget(self._table_widget, 1)
        right_top_layout.addWidget(self._settings_scroll)

        right_vertical = QSplitter(Qt.Orientation.Vertical, self)
        right_vertical.addWidget(right_top)
        right_vertical.addWidget(self._raw_stream_widget)
        right_vertical.setSizes([460, 260])

        self._main_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._main_splitter.addWidget(left_splitter)
        self._main_splitter.addWidget(right_vertical)
        self._main_splitter.setSizes([980, 380])

        root_layout.addLayout(top_controls_row)
        root_layout.addWidget(self._main_splitter, 1)
        self.setCentralWidget(root)

        self._set_connect_indicator(False)
        self._set_record_button_state(False)

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
        self._connect_button.clicked.connect(self._toggle_connection)
        self._record_button.clicked.connect(self._toggle_recording)
        self._capacity_spin.valueChanged.connect(self._on_capacity_changed)
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

        self._file_import_csv_action.triggered.connect(self._load_playback_csv)
        self._file_export_data_action.triggered.connect(self._export_record_batches)
        self._file_exit_action.triggered.connect(self.close)
        self._tools_toggle_filter_action.triggered.connect(self._toggle_filter_panel)
        self._tools_clear_filter_action.triggered.connect(self._clear_filter_steps)
        self._settings_choose_dir_action.triggered.connect(self._choose_default_record_dir)
        self._settings_reset_dir_action.triggered.connect(self._reset_default_record_dir)
        self._help_protocol_action.triggered.connect(self._show_protocol_help)
        self._help_about_action.triggered.connect(self._show_about)

        self._port_combo.popup_opened.connect(self._serial_controller.on_port_combo_popup)
        self._port_combo.popup_closed.connect(self._serial_controller.on_port_combo_hide)

        self._bridge.data_received.connect(self._on_data_received)
        self._serial_manager.register_callback(self._on_serial_payload)

    def _apply_dark_theme(self) -> None:
        self.setStyleSheet(
            "QMainWindow { background-color: #0F0F0F; }"
            "QLabel { color: #EAEAEA; }"
            "QComboBox, QPushButton, QSpinBox, QDoubleSpinBox { background-color: #1A1A1A; color: #EAEAEA; border: 1px solid #2A2A2A; border-radius: 4px; padding: 6px 8px; }"
            "QComboBox QAbstractItemView { background-color: #1A1A1A; color: #EAEAEA; border: 1px solid #2A2A2A; selection-background-color: #2A2A2A; selection-color: #FFFFFF; }"
            "QComboBox::item { color: #EAEAEA; }"
            "QPushButton:hover { background-color: #242424; }"
            "QStatusBar { background-color: #141414; color: #D0D0D0; border-top: 1px solid #2A2A2A; }"
            "QSplitter::handle { background: #202020; }"
            "QMenuBar { background-color: #161616; color: #EAEAEA; }"
            "QMenuBar::item:selected { background-color: #242424; }"
            "QMenu { background-color: #1A1A1A; color: #EAEAEA; border: 1px solid #2A2A2A; }"
            "QMenu::item:selected { background-color: #2A2A2A; }"
        )

    def _set_connect_indicator(self, connected: bool, blinking: bool = False) -> None:
        if not connected:
            color = "#808080"
        elif blinking:
            color = "#808080"
        else:
            color = "#2EDB6E"
        self._connect_button.setStyleSheet(
            f"QPushButton {{ background-color: {color}; border: 2px solid #101010; border-radius: 10px; padding: 0; }}"
            "QPushButton:hover { border: 2px solid #FFFFFF; }"
        )

    def _blink_connect_indicator(self) -> None:
        if not self._connected:
            self._set_connect_indicator(False)
            return
        self._set_connect_indicator(True, blinking=True)
        QTimer.singleShot(170, lambda: self._set_connect_indicator(True, blinking=False) if self._connected else self._set_connect_indicator(False))

    def _set_record_button_state(self, recording: bool) -> None:
        if recording:
            self._record_button.setText("结束录制")
            self._record_button.setStyleSheet(
                "QPushButton { background-color: #C62828; color: #FFFFFF; border: 1px solid #8E0000; border-radius: 4px; padding: 6px 10px; }"
            )
        else:
            self._record_button.setText("开始录制")
            self._record_button.setStyleSheet("")

    def refresh_ports(self) -> None:
        self._serial_controller.refresh_ports()

    def _toggle_connection(self) -> None:
        self._serial_controller.toggle_connection()

    def _connect_serial(self) -> None:
        self._serial_controller.connect_serial()

    def _disconnect_serial(self) -> None:
        self._serial_controller.disconnect_serial()

    def _on_serial_payload(self, payload: list[int], frame_no: int, timestamp: float) -> None:
        self._serial_controller.on_serial_payload(payload, frame_no, timestamp)

    def _on_data_received(self, payload: list[int], frame_no: int, _timestamp: float) -> None:
        self._serial_controller.on_data_received(payload, frame_no, _timestamp)
        self._refresh_export_action_state()

    def _on_capacity_changed(self, value: int) -> None:
        self._recording_controller.on_capacity_changed(value)

    def _build_auto_filename(self) -> str:
        return self._recording_controller.build_auto_filename()

    def _toggle_recording(self) -> None:
        self._recording_controller.toggle_recording()
        self._refresh_export_action_state()

    def _stop_recording_and_export(self) -> None:
        self._recording_controller.stop_recording_and_store_batch()
        self._refresh_export_action_state()

    def _calculate_record_metrics(self) -> tuple[float, float]:
        return self._recording_controller.calculate_record_metrics()

    def _update_record_runtime_label(self) -> None:
        self._recording_controller.update_record_runtime_label()

    def _handle_unsaved_recording_before_interrupt(self) -> None:
        self._recording_controller.handle_unsaved_recording_before_interrupt()

    def _load_playback_csv(self) -> None:
        self._playback_controller.load_playback_csv()

    def _show_playback_frame(self, index: int) -> None:
        self._playback_controller.show_playback_frame(index)

    def _show_prev_playback_frame(self) -> None:
        self._playback_controller.show_prev_playback_frame()

    def _show_next_playback_frame(self) -> None:
        self._playback_controller.show_next_playback_frame()

    def _apply_playback_speed(self) -> None:
        self._playback_controller.apply_playback_speed()

    def _toggle_playback(self) -> None:
        self._playback_controller.toggle_playback()

    def _playback_tick(self) -> None:
        self._playback_controller.playback_tick()

    def _on_playback_slider_changed(self, value: int) -> None:
        self._playback_controller.on_playback_slider_changed(value)

    def _refresh_filter_step_ui(self) -> None:
        self._filter_controller.refresh_filter_step_ui()

    def _on_add_filter_step(self) -> None:
        self._filter_controller.on_add_filter_step()

    def _on_remove_filter_step(self) -> None:
        self._filter_controller.on_remove_filter_step()

    def _on_move_filter_step_up(self) -> None:
        self._filter_controller.on_move_filter_step_up()

    def _on_move_filter_step_down(self) -> None:
        self._filter_controller.on_move_filter_step_down()

    def _on_filter_step_selected(self, index: int) -> None:
        self._filter_controller.on_filter_step_selected(index)

    def _on_filter_param_key_changed(self, key: str) -> None:
        self._filter_controller.on_filter_param_key_changed(key)

    def _configure_param_editor(self, key: str, value: float) -> None:
        self._filter_controller.configure_param_editor(key, value)

    def _on_apply_filter_param(self) -> None:
        self._filter_controller.on_apply_filter_param()

    def _recompute_current_view_with_filters(self) -> None:
        self._filter_controller.recompute_current_view_with_filters()

    def _apply_pipeline_safe(self, raw_data: list[int]) -> list[int]:
        return self._filter_controller.apply_pipeline_safe(raw_data)

    def _export_record_batches(self) -> None:
        self._recording_controller.export_batches()
        self._refresh_export_action_state()

    def _refresh_export_action_state(self) -> None:
        self._file_export_data_action.setEnabled(bool(self._record_batches))

    def _toggle_filter_panel(self) -> None:
        self._filter_panel.setVisible(not self._filter_panel.isVisible())

    def _clear_filter_steps(self) -> None:
        steps = self._filter_pipeline.get_steps()
        for _ in range(len(steps)):
            self._filter_step_combo.setCurrentIndex(0)
            self._filter_controller.on_remove_filter_step()

    def _choose_default_record_dir(self) -> None:
        self._recording_controller.choose_default_record_dir()

    def _reset_default_record_dir(self) -> None:
        self._recording_controller.reset_default_record_dir()

    def _show_protocol_help(self) -> None:
        QMessageBox.information(
            self,
            "协议说明",
            "帧头: 0xAA 0x55\n"
            "长度字段: 128\n"
            "负载: 128字节灰度数据(0~255)\n"
            "校验: (length + sum(payload)) & 0xFF\n"
            "异常帧: 丢弃并继续解析下一帧",
        )

    def _show_about(self) -> None:
        QMessageBox.information(self, "关于", "EasyCCD 上位机\n用于CCD串口数据采集、回放与分析。")

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._recording_controller.handle_unsaved_recording_before_interrupt()
        self._port_fast_refresh_timer.stop()
        self._port_slow_refresh_timer.stop()
        self._serial_manager.close()
        super().closeEvent(event)
