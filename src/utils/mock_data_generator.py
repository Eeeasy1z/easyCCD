from __future__ import annotations

import math
import random
import struct
import threading
import time
from collections.abc import Callable, Iterable


HEADER = b"\xAA\x55"
PAYLOAD_LEN = 128


def _clamp_to_byte(value: float) -> int:
    return max(0, min(255, int(round(value))))


def generate_simulation_data(
    *,
    peak_center: float | None = None,
    peak_width: float = 14.0,
    dark_level: int = 20,
    bright_level: int = 235,
    noise_level: float = 8.0,
) -> list[int]:
    if peak_width <= 0:
        raise ValueError("peak_width must be > 0")
    if dark_level > bright_level:
        raise ValueError("dark_level must be <= bright_level")

    center = peak_center if peak_center is not None else (PAYLOAD_LEN - 1) / 2 + random.uniform(-8.0, 8.0)
    sigma = peak_width
    data: list[int] = []
    for index in range(PAYLOAD_LEN):
        distance = index - center
        gaussian = math.exp(-(distance * distance) / (2.0 * sigma * sigma))
        base = dark_level + (bright_level - dark_level) * gaussian
        noisy = base + random.uniform(-noise_level, noise_level)
        data.append(_clamp_to_byte(noisy))
    return data


def generate_ccd_frame(payload: Iterable[int] | None = None) -> bytes:
    payload_bytes = bytes(generate_simulation_data() if payload is None else payload)
    if len(payload_bytes) != PAYLOAD_LEN:
        raise ValueError(f"payload length must be {PAYLOAD_LEN}")
    checksum = (PAYLOAD_LEN + sum(payload_bytes)) & 0xFF
    return struct.pack(f"<2sB{PAYLOAD_LEN}sB", HEADER, PAYLOAD_LEN, payload_bytes, checksum)


class MockSerialSender:
    def __init__(self, send_func: Callable[[bytes], None], interval: float = 0.05) -> None:
        if not callable(send_func):
            raise TypeError("send_func must be callable")
        if interval <= 0:
            raise ValueError("interval must be > 0")
        self._send_func = send_func
        self._interval = interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def send_once(self) -> bytes:
        frame = generate_ccd_frame()
        self._send_func(frame)
        return frame

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="MockSerialSenderThread", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self.send_once()
            time.sleep(self._interval)
