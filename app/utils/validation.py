from __future__ import annotations

import math
from typing import Any


def validate_regions(regions, vulnerability):
    for r in regions:
        if r not in vulnerability:
            raise ValueError(f"Missing vulnerability value for region: {r}")


def ensure_finite_number(value: Any, *, field_name: str = "value") -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a number, not boolean")

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a numeric value") from None

    if not math.isfinite(numeric):
        raise ValueError(f"{field_name} must be finite")

    return numeric


def parse_number_list(values: Any, *, field_name: str = "numbers") -> list[float]:
    if not isinstance(values, list):
        raise ValueError(f"payload.{field_name} must be a list")

    return [
        ensure_finite_number(item, field_name=f"payload.{field_name}[{idx}]")
        for idx, item in enumerate(values)
    ]
