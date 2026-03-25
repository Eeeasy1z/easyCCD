from __future__ import annotations

from .base import FilterBase


class MedianFilter(FilterBase):
    name = "median"
    default_params = {"window": 5}

    def apply(self, data: list[int], params: dict[str, int | float] | None = None) -> list[int]:
        if not data:
            return []
        cfg = dict(self.default_params)
        if params:
            cfg.update(params)
        window = self._sanitize_window(cfg.get("window", 5))
        radius = window // 2
        n = len(data)
        output: list[int] = []
        for i in range(n):
            values = []
            for k in range(-radius, radius + 1):
                idx = self._mirror_index(i + k, n)
                values.append(int(data[idx]))
            values.sort()
            output.append(values[radius])
        return self._clamp_uint8(output)
