from __future__ import annotations


THRESHOLD_METHOD_FIXED = "fixed"
THRESHOLD_METHOD_MEAN = "mean"
THRESHOLD_METHOD_OTSU = "otsu"
THRESHOLD_METHOD_ITERATIVE = "iterative"
THRESHOLD_METHOD_PERCENTILE = "percentile"
THRESHOLD_METHOD_GRADIENT = "gradient"


def compute_threshold(
    payload: list[int],
    method: str,
    fixed_value: int = 128,
    gradient_window_radius: int = 3,
) -> int:
    normalized = _normalize_payload(payload)
    if not normalized:
        return _clamp_uint8(fixed_value)

    if method == THRESHOLD_METHOD_MEAN:
        return _compute_mean_threshold(normalized)
    if method == THRESHOLD_METHOD_OTSU:
        return _compute_otsu_threshold(normalized)
    if method == THRESHOLD_METHOD_ITERATIVE:
        return _compute_iterative_threshold(normalized)
    if method == THRESHOLD_METHOD_PERCENTILE:
        return _compute_percentile_threshold(normalized)
    if method == THRESHOLD_METHOD_GRADIENT:
        return _compute_gradient_threshold(normalized, gradient_window_radius=gradient_window_radius)
    return _clamp_uint8(fixed_value)


def _normalize_payload(payload: list[int]) -> list[int]:
    return [_clamp_uint8(value) for value in payload]


def _clamp_uint8(value: int) -> int:
    return max(0, min(255, int(value)))


def _compute_mean_threshold(payload: list[int]) -> int:
    if not payload:
        return 128
    return int(round(sum(payload) / len(payload)))


def _compute_otsu_threshold(payload: list[int]) -> int:
    if not payload:
        return 128

    histogram = [0] * 256
    for value in payload:
        histogram[value] += 1

    total = len(payload)
    sum_total = 0
    for level, count in enumerate(histogram):
        sum_total += level * count

    background_weight = 0
    background_sum = 0
    max_between_class_variance = -1.0
    best_threshold = 0

    for threshold in range(256):
        background_weight += histogram[threshold]
        if background_weight == 0:
            continue

        foreground_weight = total - background_weight
        if foreground_weight == 0:
            break

        background_sum += threshold * histogram[threshold]
        background_mean = background_sum / background_weight
        foreground_mean = (sum_total - background_sum) / foreground_weight
        mean_delta = background_mean - foreground_mean
        between_class_variance = background_weight * foreground_weight * mean_delta * mean_delta

        if between_class_variance > max_between_class_variance:
            max_between_class_variance = between_class_variance
            best_threshold = threshold

    return best_threshold


def _compute_iterative_threshold(payload: list[int]) -> int:
    if not payload:
        return 128

    threshold = _compute_mean_threshold(payload)
    for _ in range(32):
        lower_group = [value for value in payload if value <= threshold]
        upper_group = [value for value in payload if value > threshold]

        if not lower_group or not upper_group:
            break

        lower_mean = sum(lower_group) / len(lower_group)
        upper_mean = sum(upper_group) / len(upper_group)
        next_threshold = int(round((lower_mean + upper_mean) / 2.0))
        if next_threshold == threshold:
            break
        threshold = next_threshold

    return _clamp_uint8(threshold)


def _compute_percentile_threshold(payload: list[int], percentile: float = 0.5) -> int:
    if not payload:
        return 128

    sorted_values = sorted(payload)
    normalized_percentile = max(0.0, min(1.0, float(percentile)))
    index = int(round((len(sorted_values) - 1) * normalized_percentile))
    return _clamp_uint8(sorted_values[index])


def _compute_gradient_threshold(payload: list[int], gradient_window_radius: int = 3) -> int:
    if len(payload) < 3:
        return _compute_mean_threshold(payload)

    strongest_index = 1
    strongest_magnitude = -1
    for idx in range(1, len(payload) - 1):
        gradient = (-payload[idx - 1]) + payload[idx + 1]
        magnitude = abs(gradient)
        if magnitude > strongest_magnitude:
            strongest_magnitude = magnitude
            strongest_index = idx

    window_radius = max(1, int(gradient_window_radius))
    left_start = max(0, strongest_index - window_radius)
    left_end = strongest_index
    right_start = strongest_index + 1
    right_end = min(len(payload), strongest_index + 1 + window_radius)

    left_group = payload[left_start:left_end]
    right_group = payload[right_start:right_end]

    if not left_group or not right_group:
        return _compute_mean_threshold(payload)

    left_mean = sum(left_group) / len(left_group)
    right_mean = sum(right_group) / len(right_group)
    threshold = int(round((left_mean + right_mean) / 2.0))
    return _clamp_uint8(threshold)
