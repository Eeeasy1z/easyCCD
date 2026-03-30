from __future__ import annotations

from dataclasses import dataclass, field

from core.filters import GaussianFilter, MeanFilter, MedianFilter
from core.filters.base import FilterBase


@dataclass
class FilterStep:
    filter_name: str
    params: dict[str, int | float] = field(default_factory=dict)


class FilterPipeline:
    def __init__(self) -> None:
        self._registry: dict[str, FilterBase] = {
            MeanFilter.name: MeanFilter(),
            MedianFilter.name: MedianFilter(),
            GaussianFilter.name: GaussianFilter(),
        }
        self._steps: list[FilterStep] = []

    def get_available_filters(self) -> list[str]:
        return list(self._registry.keys())

    def get_default_params(self, filter_name: str) -> dict[str, int | float]:
        if filter_name not in self._registry:
            raise KeyError(f"Unknown filter: {filter_name}")
        return dict(self._registry[filter_name].default_params)

    def get_steps(self) -> list[FilterStep]:
        return [FilterStep(step.filter_name, dict(step.params)) for step in self._steps]

    def clear(self) -> None:
        self._steps.clear()

    def add_step(self, filter_name: str, params: dict[str, int | float] | None = None) -> None:
        if filter_name not in self._registry:
            raise KeyError(f"Unknown filter: {filter_name}")
        base_params = dict(self._registry[filter_name].default_params)
        if params:
            base_params.update(params)
        self._steps.append(FilterStep(filter_name, base_params))

    def remove_step(self, index: int) -> None:
        if 0 <= index < len(self._steps):
            del self._steps[index]

    def move_up(self, index: int) -> None:
        if 0 < index < len(self._steps):
            self._steps[index - 1], self._steps[index] = self._steps[index], self._steps[index - 1]

    def move_down(self, index: int) -> None:
        if 0 <= index < len(self._steps) - 1:
            self._steps[index + 1], self._steps[index] = self._steps[index], self._steps[index + 1]

    def update_step_params(self, index: int, params: dict[str, int | float]) -> None:
        if 0 <= index < len(self._steps):
            self._steps[index].params.update(params)

    def apply(self, data: list[int]) -> list[int]:
        output = list(data)
        for step in self._steps:
            flt = self._registry.get(step.filter_name)
            if flt is None:
                continue
            output = flt.apply(output, step.params)
        if len(output) < len(data):
            output.extend([0] * (len(data) - len(output)))
        return output[: len(data)]

    def apply_with_stages(self, data: list[int]) -> list[tuple[str, list[int]]]:
        stages: list[tuple[str, list[int]]] = []
        output = list(data)
        for step in self._steps:
            flt = self._registry.get(step.filter_name)
            if flt is None:
                continue
            output = flt.apply(output, step.params)
            if len(output) < len(data):
                output = output + ([0] * (len(data) - len(output)))
            normalized = output[: len(data)]
            stages.append((step.filter_name, normalized))
            output = normalized
        return stages
