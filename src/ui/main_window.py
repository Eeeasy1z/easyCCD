from __future__ import annotations

from collections import deque
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QFontMetrics, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHeaderView,
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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from comm.serial_manager import SerialManager
from core.filter_pipeline import FilterPipeline
from ui.controllers import FilterController, PlaybackController, RecordingController, SerialController, ThresholdController
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


class NoWheelSpinBox(QSpinBox):
    def wheelEvent(self, event) -> None:  # type: ignore[override]
        event.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event) -> None:  # type: ignore[override]
        event.ignore()


class SerialSignalBridge(QObject):
    data_received = Signal(list, int, float)
    connect_result = Signal(bool, str, str, int, int)
    disconnect_result = Signal(bool, int)


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
        self._playback_batch_ids: list[int] = []
        self._playback_index = -1
        self._playback_timer = QTimer(self)
        self._playback_playing = False
        self._filter_pipeline = FilterPipeline()
        self._last_raw_payload: list[int] = []
        self._latest_filtered_payload: list[int] = []
        self._last_filter_error = ""
        self._threshold_mode = "manual"
        self._threshold_method = "otsu"
        self._threshold_manual_value = 128
        self._current_threshold = 128
        self._threshold_gradient_window_radius = 3
        self._threshold_invert = False

        self._recording_controller = RecordingController(self)
        self._playback_controller = PlaybackController(self)
        self._filter_controller = FilterController(self)
        self._serial_controller = SerialController(self)
        self._threshold_controller = ThresholdController(self)

        self._playback_timer.timeout.connect(self._playback_tick)
        self._port_fast_refresh_timer = QTimer(self)
        self._port_fast_refresh_timer.setInterval(500)
        self._port_fast_refresh_timer.timeout.connect(self._serial_controller.on_port_fast_tick)
        self._port_slow_refresh_timer = QTimer(self)
        self._port_slow_refresh_timer.setInterval(10000)
        self._port_slow_refresh_timer.timeout.connect(self._serial_controller.on_port_slow_tick)
        self._connect_watchdog_timer = QTimer(self)
        self._connect_watchdog_timer.setSingleShot(True)
        self._connect_watchdog_timer.setInterval(5000)
        self._connect_watchdog_timer.timeout.connect(self._serial_controller.on_connect_timeout)

        self._build_menu_bar()
        self._build_ui()
        self._connect_signals()
        self._refresh_filter_step_ui()
        self._threshold_controller.on_threshold_mode_changed(self._threshold_mode)
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
        self._play_pause_button.setStyleSheet("font-size: 18px; font-weight: 700; padding: 4px 8px;")
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

        self._capacity_spin = NoWheelSpinBox(self)
        self._capacity_spin.setRange(100, 200000)
        self._capacity_spin.setSingleStep(100)
        self._capacity_spin.setValue(self._record_capacity)
        self._capacity_spin.setSuffix(" 帧")

        self._filter_panel = QWidget(self)
        filter_panel_layout = QVBoxLayout(self._filter_panel)
        filter_panel_layout.setContentsMargins(2, 4, 2, 4)
        filter_panel_layout.setSpacing(8)

        filter_title = QLabel("滤波配置", self)
        filter_title.setStyleSheet("padding-left: 8px;")
        filter_panel_layout.addWidget(filter_title)

        available_title = QLabel("可用滤波器:", self)
        available_title.setStyleSheet("padding-left: 8px;")
        filter_panel_layout.addWidget(available_title)

        available_row = QHBoxLayout()
        available_row.setContentsMargins(0, 0, 0, 0)
        available_row.setSpacing(6)
        self._available_filter_combo = NoWheelComboBox(self)
        self._available_filter_combo.addItems(self._filter_pipeline.get_available_filters())
        self._available_filter_combo.setMinimumWidth(130)
        self._add_filter_button = QPushButton("添加", self)
        self._add_filter_button.setFixedWidth(56)
        self._add_filter_button.setFixedHeight(30)
        available_row.addWidget(self._available_filter_combo, 1)
        available_row.addWidget(self._add_filter_button)
        filter_panel_layout.addLayout(available_row)

        chain_title = QLabel("滤波管道:", self)
        chain_title.setStyleSheet("padding-left: 8px;")
        filter_panel_layout.addWidget(chain_title)

        pipeline_row = QHBoxLayout()
        pipeline_row.setContentsMargins(0, 0, 0, 0)
        pipeline_row.setSpacing(6)
        self._filter_pipeline_table = QTableWidget(0, 1, self)
        self._filter_pipeline_table.setHorizontalHeaderLabels([""])
        self._filter_pipeline_table.horizontalHeader().setVisible(False)
        self._filter_pipeline_table.verticalHeader().setVisible(False)
        self._filter_pipeline_table.setAlternatingRowColors(True)
        self._filter_pipeline_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._filter_pipeline_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._filter_pipeline_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._filter_pipeline_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._filter_pipeline_table.setStyleSheet(
            "QTableWidget { background-color: #111111; color: #EAEAEA; gridline-color: #2A2A2A; border: 1px solid #2A2A2A; alternate-background-color: #181818; selection-background-color: #2A2A2A; selection-color: #FFFFFF; }"
            "QHeaderView::section { background-color: #1E1E1E; color: #EAEAEA; border: 1px solid #2A2A2A; padding: 4px; }"
            "QTableWidget::item { color: #EAEAEA; padding-left: 8px; padding-right: 8px; }"
            "QTableWidget::item:selected { background-color: #2A2A2A; color: #FFFFFF; }"
        )

        op_button_col = QVBoxLayout()
        op_button_col.setContentsMargins(0, 0, 0, 0)
        op_button_col.setSpacing(6)
        self._remove_filter_button = QPushButton("删除", self)
        self._remove_filter_button.setFixedWidth(56)
        self._remove_filter_button.setFixedHeight(30)
        self._move_up_button = QPushButton("上移", self)
        self._move_up_button.setFixedWidth(56)
        self._move_up_button.setFixedHeight(30)
        self._move_down_button = QPushButton("下移", self)
        self._move_down_button.setFixedWidth(56)
        self._move_down_button.setFixedHeight(30)
        op_button_col.addWidget(self._remove_filter_button)
        op_button_col.addWidget(self._move_up_button)
        op_button_col.addWidget(self._move_down_button)
        op_button_col.addStretch(1)

        button_block_height = (30 * 3) + (6 * 2)
        self._filter_pipeline_table.setFixedHeight(button_block_height)

        pipeline_row.addWidget(self._filter_pipeline_table, 1)
        pipeline_row.addLayout(op_button_col)
        filter_panel_layout.addLayout(pipeline_row)

        param_key_title = QLabel("参数项:", self)
        param_key_title.setStyleSheet("padding-left: 8px;")
        filter_panel_layout.addWidget(param_key_title)
        self._param_key_combo = NoWheelComboBox(self)
        filter_panel_layout.addWidget(self._param_key_combo)

        param_value_title = QLabel("参数值:", self)
        param_value_title.setStyleSheet("padding-left: 8px;")
        filter_panel_layout.addWidget(param_value_title)
        self._param_value_spin = NoWheelDoubleSpinBox(self)
        self._param_value_spin.setDecimals(3)
        self._param_value_spin.setRange(-1000.0, 1000.0)
        filter_panel_layout.addWidget(self._param_value_spin)

        self._apply_param_button = QPushButton("应用参数", self)
        self._apply_param_button.setMinimumHeight(30)
        filter_panel_layout.addWidget(self._apply_param_button)

        threshold_title = QLabel("阈值计算:", self)
        threshold_title.setStyleSheet("padding-left: 8px;")
        filter_panel_layout.addWidget(threshold_title)

        threshold_mode_row = QHBoxLayout()
        threshold_mode_row.setContentsMargins(0, 0, 0, 0)
        threshold_mode_row.setSpacing(6)
        threshold_mode_row.addWidget(QLabel("模式:", self))
        self._threshold_mode_combo = NoWheelComboBox(self)
        self._threshold_mode_combo.addItem("手动", "manual")
        self._threshold_mode_combo.addItem("自动", "auto")
        self._threshold_mode_combo.setCurrentIndex(0)
        threshold_mode_row.addWidget(self._threshold_mode_combo, 1)
        filter_panel_layout.addLayout(threshold_mode_row)

        threshold_method_row = QHBoxLayout()
        threshold_method_row.setContentsMargins(0, 0, 0, 0)
        threshold_method_row.setSpacing(6)
        self._threshold_method_title_label = QLabel("方法:", self)
        threshold_method_row.addWidget(self._threshold_method_title_label)
        self._threshold_method_combo = NoWheelComboBox(self)
        self._threshold_method_combo.addItem("平均值", "mean")
        self._threshold_method_combo.addItem("Otsu", "otsu")
        self._threshold_method_combo.addItem("迭代", "iterative")
        self._threshold_method_combo.addItem("百分位", "percentile")
        self._threshold_method_combo.addItem("梯度", "gradient")
        self._threshold_method_combo.setCurrentIndex(1)
        self._threshold_method_combo.setEnabled(False)
        threshold_method_row.addWidget(self._threshold_method_combo, 1)
        filter_panel_layout.addLayout(threshold_method_row)

        gradient_window_row = QHBoxLayout()
        gradient_window_row.setContentsMargins(0, 0, 0, 0)
        gradient_window_row.setSpacing(6)
        self._threshold_gradient_label = QLabel("梯度窗口:", self)
        gradient_window_row.addWidget(self._threshold_gradient_label)
        self._threshold_gradient_spin = NoWheelSpinBox(self)
        self._threshold_gradient_spin.setRange(1, 16)
        self._threshold_gradient_spin.setValue(self._threshold_gradient_window_radius)
        self._threshold_gradient_spin.setSuffix(" 点")
        self._threshold_gradient_spin.setEnabled(False)
        gradient_window_row.addWidget(self._threshold_gradient_spin, 1)
        filter_panel_layout.addLayout(gradient_window_row)

        self._threshold_manual_slider = QSlider(Qt.Orientation.Horizontal, self)
        self._threshold_manual_slider.setRange(0, 255)
        self._threshold_manual_slider.setValue(self._threshold_manual_value)
        filter_panel_layout.addWidget(self._threshold_manual_slider)

        self._threshold_manual_spin = NoWheelSpinBox(self)
        self._threshold_manual_spin.setRange(0, 255)
        self._threshold_manual_spin.setValue(self._threshold_manual_value)
        filter_panel_layout.addWidget(self._threshold_manual_spin)

        self._threshold_invert_button = QPushButton("反转: 关", self)
        self._threshold_invert_button.setMinimumHeight(28)
        filter_panel_layout.addWidget(self._threshold_invert_button)

        self._threshold_status_label = QLabel("当前阈值: 128 (手动)", self)
        self._threshold_status_label.setStyleSheet("padding-left: 8px;")
        self._threshold_status_label.setVisible(False)
        filter_panel_layout.addWidget(self._threshold_status_label)

        self._threshold_comparison_label = QLabel("对比 平均:- Otsu:- 迭代:- 百分位:- 梯度:-", self)
        self._threshold_comparison_label.setStyleSheet("padding-left: 8px;")
        self._threshold_comparison_label.setWordWrap(True)
        self._threshold_comparison_label.setVisible(False)
        filter_panel_layout.addWidget(self._threshold_comparison_label)

        self._threshold_compare_table = QTableWidget(5, 2, self)
        self._threshold_compare_table.setHorizontalHeaderLabels(["方法", "阈值"])
        self._threshold_compare_table.verticalHeader().setVisible(False)
        self._threshold_compare_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._threshold_compare_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._threshold_compare_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._threshold_compare_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._threshold_compare_table.setStyleSheet(
            "QTableWidget { background-color: #111111; color: #EAEAEA; gridline-color: #2A2A2A; border: 1px solid #2A2A2A; }"
            "QHeaderView::section { background-color: #1E1E1E; color: #EAEAEA; border: 1px solid #2A2A2A; padding: 3px; }"
            "QTableWidget::item { color: #EAEAEA; padding-left: 6px; padding-right: 6px; }"
        )
        self._threshold_compare_table.setFixedHeight(156)
        self._threshold_compare_table.setVisible(False)
        filter_panel_layout.addWidget(self._threshold_compare_table)

        self.set_threshold_compare_rows([
            ("平均值", "-"),
            ("Otsu", "-"),
            ("迭代", "-"),
            ("百分位", "-"),
            ("梯度", "-"),
        ])

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
        side_layout.setContentsMargins(10, 12, 10, 8)
        side_layout.setSpacing(10)
        cache_title = QLabel("缓存上限:", self)
        cache_title.setStyleSheet("padding-left: 8px;")
        side_layout.addWidget(cache_title)
        side_layout.addWidget(self._capacity_spin)

        batch_title = QLabel("缓存列表:", self)
        batch_title.setStyleSheet("padding-left: 8px;")
        side_layout.addWidget(batch_title)
        self._batch_list_table = QTableWidget(0, 1, self)
        self._batch_list_table.setHorizontalHeaderLabels([""])
        self._batch_list_table.horizontalHeader().setVisible(False)
        self._batch_list_table.verticalHeader().setVisible(False)
        self._batch_list_table.setAlternatingRowColors(True)
        self._batch_list_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._batch_list_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._batch_list_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._batch_list_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._batch_list_table.setStyleSheet(
            "QTableWidget { background-color: #111111; color: #EAEAEA; gridline-color: #2A2A2A; border: 1px solid #2A2A2A; alternate-background-color: #181818; selection-background-color: #2A2A2A; selection-color: #FFFFFF; }"
            "QHeaderView::section { background-color: #1E1E1E; color: #EAEAEA; border: 1px solid #2A2A2A; padding: 4px; }"
            "QTableWidget::item { color: #EAEAEA; padding-left: 8px; padding-right: 8px; }"
            "QTableWidget::item:selected { background-color: #2A2A2A; color: #FFFFFF; }"
        )
        self._batch_list_table.setFixedHeight(140)
        side_layout.addWidget(self._batch_list_table)

        batch_button_row = QHBoxLayout()
        batch_button_row.setContentsMargins(0, 0, 0, 0)
        batch_button_row.setSpacing(8)
        self._play_batch_button = QPushButton("回放", self)
        self._play_batch_button.setFixedWidth(56)
        self._play_batch_button.setFixedHeight(30)
        self._remove_batch_button = QPushButton("删除", self)
        self._remove_batch_button.setFixedWidth(56)
        self._remove_batch_button.setFixedHeight(30)
        self._play_batch_button.setEnabled(False)
        self._remove_batch_button.setEnabled(False)
        batch_button_row.addWidget(self._play_batch_button)
        batch_button_row.addWidget(self._remove_batch_button)
        side_layout.addLayout(batch_button_row)

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
        self._side_panel.setStyleSheet("background-color: #0F0F0F; color: #EAEAEA;")
        self._filter_panel.setStyleSheet("background-color: #0F0F0F; color: #EAEAEA;")
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
        self._filter_pipeline_table.itemSelectionChanged.connect(self._on_filter_step_selected)
        self._param_key_combo.currentTextChanged.connect(self._on_filter_param_key_changed)
        self._apply_param_button.clicked.connect(self._on_apply_filter_param)
        self._threshold_mode_combo.currentIndexChanged.connect(self._on_threshold_mode_changed)
        self._threshold_method_combo.currentIndexChanged.connect(self._on_threshold_method_changed)
        self._threshold_manual_slider.valueChanged.connect(self._on_threshold_manual_slider_changed)
        self._threshold_manual_spin.valueChanged.connect(self._on_threshold_manual_spin_changed)
        self._threshold_gradient_spin.valueChanged.connect(self._on_threshold_gradient_window_changed)
        self._threshold_invert_button.clicked.connect(self._on_threshold_invert_toggled)
        self._batch_list_table.itemSelectionChanged.connect(self._on_batch_selection_changed)
        self._batch_list_table.itemDoubleClicked.connect(self._play_selected_record_batch)
        self._play_batch_button.clicked.connect(self._play_selected_record_batch)
        self._remove_batch_button.clicked.connect(self._delete_selected_record_batch)

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
        self._bridge.connect_result.connect(self._on_connect_result)
        self._bridge.disconnect_result.connect(self._on_disconnect_result)
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
            "QMessageBox { background-color: #1A1A1A; }"
            "QMessageBox QLabel { color: #EAEAEA; }"
            "QMessageBox QPushButton { background-color: #2A2A2A; color: #EAEAEA; border: 1px solid #3A3A3A; border-radius: 4px; padding: 5px 10px; }"
            "QMessageBox QPushButton:hover { background-color: #343434; }"
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

    def set_status_text(self, text: str) -> None:
        self._status_label.setText(text)

    def set_connect_button_enabled(self, enabled: bool) -> None:
        self._connect_button.setEnabled(enabled)

    def set_connection_state(self, connected: bool, status_text: str | None = None) -> None:
        self._connected = connected
        self._set_connect_indicator(connected)
        if status_text is not None:
            self._status_label.setText(status_text)

    def render_frame_views(self, raw_payload: list[int], filtered_payload: list[int], frame_no: int, frame_label: str | None = None) -> None:
        self._last_raw_payload = list(raw_payload)
        self._latest_payload = list(raw_payload)
        self._latest_filtered_payload = list(filtered_payload)
        self._latest_frame_no = frame_no
        self._waveform_widget.update_curves(raw_payload, filtered_payload)
        self._threshold_controller.refresh_with_payload(filtered_payload)
        self._table_widget.update_data(filtered_payload)
        if frame_label is None:
            self._frame_label.setText(f"帧号: {frame_no}")
        else:
            self._frame_label.setText(frame_label)

    def set_stats_counts(self, received_ok: int, bad_frames: int, record_count: int) -> None:
        self._stats_label.setText(f"统计: 接收{received_ok} | 坏帧{bad_frames} | 录制{record_count}")

    def set_filter_pipeline_rows(self, names: list[str]) -> None:
        table = self._filter_pipeline_table
        table.blockSignals(True)
        table.clearContents()
        table.setRowCount(len(names))
        for idx, name in enumerate(names):
            item = QTableWidgetItem(name)
            item.setForeground(QColor("#EAEAEA"))
            item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            table.setItem(idx, 0, item)
        table.blockSignals(False)

    def set_filter_controls_enabled(self, has_steps: bool, can_add: bool) -> None:
        self._remove_filter_button.setEnabled(has_steps)
        self._move_up_button.setEnabled(has_steps)
        self._move_down_button.setEnabled(has_steps)
        self._param_key_combo.setEnabled(has_steps)
        self._param_value_spin.setEnabled(has_steps)
        self._apply_param_button.setEnabled(has_steps)
        self._add_filter_button.setEnabled(can_add)

    def select_filter_row(self, index: int) -> None:
        if 0 <= index < self._filter_pipeline_table.rowCount():
            self._filter_pipeline_table.selectRow(index)

    def clear_filter_param_keys(self) -> None:
        self._param_key_combo.clear()

    def set_filter_param_keys(self, keys: list[str]) -> None:
        self._param_key_combo.blockSignals(True)
        self._param_key_combo.clear()
        self._param_key_combo.addItems(keys)
        self._param_key_combo.blockSignals(False)

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

    def _on_connect_result(self, success: bool, message: str, port: str, baudrate: int, attempt_id: int) -> None:
        self._serial_controller.on_connect_result(success, message, port, baudrate, attempt_id)

    def _on_disconnect_result(self, success: bool, attempt_id: int) -> None:
        self._serial_controller.on_disconnect_result(success, attempt_id)

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
        self._recording_controller.handle_unsaved_batches_on_close()

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

    def _on_filter_step_selected(self, index: int | None = None) -> None:
        if isinstance(index, int):
            self._filter_controller.on_filter_step_selected(index)
            return
        self._filter_controller.on_filter_step_selected(self._get_selected_filter_step_index())

    def _get_selected_filter_step_index(self) -> int:
        selected_items = self._filter_pipeline_table.selectedItems()
        if not selected_items:
            return -1
        return selected_items[0].row()

    def _on_filter_param_key_changed(self, key: str) -> None:
        self._filter_controller.on_filter_param_key_changed(key)

    def _configure_param_editor(self, key: str, value: float) -> None:
        self._filter_controller.configure_param_editor(key, value)

    def _on_apply_filter_param(self) -> None:
        self._filter_controller.on_apply_filter_param()

    def _on_threshold_mode_changed(self, _index: int) -> None:
        mode = str(self._threshold_mode_combo.currentData())
        self._threshold_controller.on_threshold_mode_changed(mode)

    def _on_threshold_method_changed(self, _index: int) -> None:
        method = str(self._threshold_method_combo.currentData())
        self._threshold_controller.on_threshold_method_changed(method)

    def _on_threshold_manual_slider_changed(self, value: int) -> None:
        self._threshold_controller.on_threshold_manual_slider_changed(int(value))

    def _on_threshold_manual_spin_changed(self, value: int) -> None:
        self._threshold_controller.on_threshold_manual_spin_changed(int(value))

    def _on_threshold_gradient_window_changed(self, value: int) -> None:
        self._threshold_controller.on_threshold_gradient_window_changed(int(value))

    def _on_threshold_invert_toggled(self) -> None:
        self._threshold_controller.toggle_threshold_invert()

    def set_threshold_status_text(self, threshold: int, source: str) -> None:
        self._threshold_status_label.setText(f"当前阈值: {int(threshold)} ({source})")

    def set_threshold_comparison_text(self, text: str) -> None:
        self._threshold_comparison_label.setText(text)

    def set_threshold_compare_rows(self, rows: list[tuple[str, str]]) -> None:
        table = self._threshold_compare_table
        table.blockSignals(True)
        table.clearContents()
        table.setRowCount(len(rows))
        for row_idx, (method_name, threshold_text) in enumerate(rows):
            method_item = QTableWidgetItem(method_name)
            method_item.setForeground(QColor("#EAEAEA"))
            method_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            value_item = QTableWidgetItem(threshold_text)
            value_item.setForeground(QColor("#EAEAEA"))
            value_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row_idx, 0, method_item)
            table.setItem(row_idx, 1, value_item)
        table.blockSignals(False)

    def set_threshold_manual_enabled(self, enabled: bool) -> None:
        self._threshold_manual_slider.setEnabled(enabled)
        self._threshold_manual_spin.setEnabled(enabled)

    def set_threshold_method_editable(self, editable: bool) -> None:
        self._threshold_method_combo.setEnabled(editable)
        if editable:
            self._threshold_method_title_label.setStyleSheet("")
            self._threshold_method_combo.setStyleSheet("")
        else:
            self._threshold_method_title_label.setStyleSheet("color: #7A7A7A;")
            self._threshold_method_combo.setStyleSheet("QComboBox { color: #7A7A7A; }")

    def set_threshold_gradient_control_enabled(self, enabled: bool) -> None:
        self._threshold_gradient_spin.setEnabled(enabled)
        if enabled:
            self._threshold_gradient_label.setStyleSheet("")
            self._threshold_gradient_spin.setStyleSheet("")
        else:
            self._threshold_gradient_label.setStyleSheet("color: #7A7A7A;")
            self._threshold_gradient_spin.setStyleSheet("QSpinBox { color: #7A7A7A; }")

    def set_threshold_invert_state(self, enabled: bool) -> None:
        self._threshold_invert = bool(enabled)
        self._threshold_invert_button.setText("反转: 开" if enabled else "反转: 关")

    def _recompute_current_view_with_filters(self) -> None:
        self._filter_controller.recompute_current_view_with_filters()

    def _apply_pipeline_safe(self, raw_data: list[int]) -> list[int]:
        return self._filter_controller.apply_pipeline_safe(raw_data)

    def _export_record_batches(self) -> None:
        self._recording_controller.export_batches()
        self._refresh_export_action_state()

    def _refresh_export_action_state(self) -> None:
        self._file_export_data_action.setEnabled(bool(self._record_batches))

    def _on_batch_selection_changed(self) -> None:
        has_selection = bool(self._batch_list_table.selectedItems())
        self._play_batch_button.setEnabled(has_selection)
        self._remove_batch_button.setEnabled(has_selection)

    def _play_selected_record_batch(self, *_args) -> None:
        self._recording_controller.play_selected_batch()

    def _delete_selected_record_batch(self) -> None:
        self._recording_controller.delete_selected_batch()

    def get_selected_batch_index(self) -> int:
        row = self._batch_list_table.currentRow()
        if row < 0:
            return -1
        return row

    def _toggle_filter_panel(self) -> None:
        self._filter_panel.setVisible(not self._filter_panel.isVisible())

    def _clear_filter_steps(self) -> None:
        steps = self._filter_pipeline.get_steps()
        for _ in range(len(steps)):
            if self._filter_pipeline_table.rowCount() > 0:
                self._filter_pipeline_table.selectRow(0)
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
        QMessageBox.information(self, "关于", "EasyCCD 上位机\n版本: V1.0")

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._serial_controller.prepare_shutdown()
        self._recording_controller.handle_unsaved_batches_on_close()
        self._port_fast_refresh_timer.stop()
        self._port_slow_refresh_timer.stop()
        self._connect_watchdog_timer.stop()
        self._serial_controller.disconnect_serial(async_mode=False)
        super().closeEvent(event)
