from __future__ import annotations

import threading
import time
from collections.abc import Callable

import serial
from serial.tools import list_ports

class SerialManager:
    HEADER = b"\xAA\x55"
    PAYLOAD_LEN = 128
    FRAME_LEN = 2 + 1 + PAYLOAD_LEN + 1

    def __init__(self) -> None:
        self._serial: serial.Serial | None = None
        self._receive_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._callback: Callable[[list[int], int, float], None] | None = None
        self._frame_counter = 0
        self._received_frame_count = 0
        self._bad_frame_count = 0
        self._buffer = bytearray()
        self._lock = threading.Lock()

    def scan_ports(self) -> list[str]:
        return [port.device for port in list_ports.comports()]

    def open(self, port: str, baudrate: int) -> None:
        self.close()
        with self._lock:
            self._serial = serial.Serial(port=port, baudrate=baudrate, timeout=0.2)
            self._frame_counter = 0
            self._received_frame_count = 0
            self._bad_frame_count = 0
            self._buffer.clear()

    def close(self) -> None:
        self.stop_receiving()
        with self._lock:
            if self._serial is not None:
                try:
                    if self._serial.is_open:
                        self._serial.close()
                finally:
                    self._serial = None
            self._buffer.clear()

    def start_receiving(self) -> None:
        with self._lock:
            if self._serial is None or not self._serial.is_open:
                raise RuntimeError("Serial port is not open")
            if self._receive_thread is not None and self._receive_thread.is_alive():
                return
            self._stop_event.clear()
            self._receive_thread = threading.Thread(
                target=self._receive_loop,
                name="SerialManagerReceiveThread",
                daemon=True,
            )
            self._receive_thread.start()

    def stop_receiving(self) -> None:
        self._stop_event.set()
        if self._receive_thread is not None and self._receive_thread.is_alive():
            self._receive_thread.join(timeout=1.0)
        self._receive_thread = None

    def register_callback(self, callback: Callable[[list[int], int, float], None]) -> None:
        if not callable(callback):
            raise TypeError("callback must be callable")
        self._callback = callback

    def get_stats(self) -> tuple[int, int, int]:
        return (self._frame_counter, self._received_frame_count, self._bad_frame_count)

    def _receive_loop(self) -> None:
        while not self._stop_event.is_set():
            current_serial = self._serial
            if current_serial is None or not current_serial.is_open:
                break
            try:
                chunk = current_serial.read(current_serial.in_waiting or 1)
            except (serial.SerialException, OSError):
                self._stop_event.set()
                break
            if not chunk:
                continue
            self._buffer.extend(chunk)
            self._parse_frames_from_buffer()

    def _parse_frames_from_buffer(self) -> None:
        while True:
            if len(self._buffer) < self.FRAME_LEN:
                return
            header_index = self._buffer.find(self.HEADER)
            if header_index == -1:
                self._buffer.clear()
                return
            if header_index > 0:
                del self._buffer[:header_index]
            if len(self._buffer) < self.FRAME_LEN:
                return
            frame = self._buffer[: self.FRAME_LEN]
            length = frame[2]
            if length != self.PAYLOAD_LEN:
                self._bad_frame_count += 1
                del self._buffer[0]
                continue
            payload = frame[3 : 3 + self.PAYLOAD_LEN]
            checksum = frame[-1]
            expected_checksum = (length + sum(payload)) & 0xFF
            if checksum != expected_checksum:
                self._bad_frame_count += 1
                del self._buffer[0]
                continue
            del self._buffer[: self.FRAME_LEN]
            self._received_frame_count += 1
            self._frame_counter += 1
            callback = self._callback
            if callback is not None:
                try:
                    callback(list(payload), self._frame_counter, time.time())
                except Exception:
                    continue
