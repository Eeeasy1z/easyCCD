from __future__ import annotations

import math

from .base import FilterBase


class GaussianFilter(FilterBase):
    name = "gaussian"
    default_params = {"sigma": 1.0}

    def apply(self, data: list[int], params: dict[str, int | float] | None = None) -> list[int]:
        if not data:
            return []
        cfg = dict(self.default_params)
        if params:
            cfg.update(params)
        sigma_raw = cfg.get("sigma", 1.0)
        try:
            sigma = float(sigma_raw)
        except (TypeError, ValueError):
            sigma = 1.0
        if sigma <= 0:
            sigma = 1.0

        radius = max(1, int(math.ceil(3 * sigma)))
        kernel = []
        for k in range(-radius, radius + 1):
            kernel.append(math.exp(-(k * k) / (2 * sigma * sigma)))
        kernel_sum = sum(kernel)
        kernel = [v / kernel_sum for v in kernel]

        n = len(data)
        output: list[int] = []
        for i in range(n):
            acc = 0.0
            for offset, weight in enumerate(kernel):
                k = offset - radius
                idx = self._mirror_index(i + k, n)
                acc += weight * int(data[idx])
            output.append(round(acc))
        return self._clamp_uint8(output)
