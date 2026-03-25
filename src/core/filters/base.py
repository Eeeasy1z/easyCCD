from __future__ import annotations

from abc import ABC, abstractmethod


class FilterBase(ABC):
    name: str = "base"
    default_params: dict[str, int | float] = {}

    @abstractmethod
    def apply(self, data: list[int], params: dict[str, int | float] | None = None) -> list[int]:
        raise NotImplementedError

    @staticmethod
    def _clamp_uint8(data: list[int]) -> list[int]:
        return [max(0, min(255, int(v))) for v in data]

    @staticmethod
    def _sanitize_window(value: int | float, default: int = 5) -> int:
        try:
            window = int(value)
        except (TypeError, ValueError):
            window = default
        if window < 3:
            window = 3
        if window % 2 == 0:
            window += 1
        return window

    @staticmethod
    def _mirror_index(index: int, length: int) -> int:
        if length <= 1:
            return 0
        while index < 0 or index >= length:
            if index < 0:
                index = -index
            if index >= length:
                index = 2 * length - index - 2
        return index
