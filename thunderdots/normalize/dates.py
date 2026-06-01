from __future__ import annotations

import re
from typing import Any


YEAR_OR_RANGE_RE = re.compile(
    r"^\s*(?P<start>-?\d{1,4})(?P<start_approx>[~?])?"
    r"(?:/(?P<end>-?\d{1,4})?(?P<end_approx>[~?])?)?\s*$"
)


TEMPORAL_FIELDS = {
    "dublincore.date",
    "dublincore.created",
    "dublincore.issued",
    "dublincore.coverage",
    "extensions.dateCreated",
    "extensions.datePublished",
    "extensions.temporalCoverage",
}


def _year_start_iso(year: int) -> str:
    return f"{year:04d}-01-01" if year >= 0 else str(year)


def _year_end_iso(year: int) -> str:
    return f"{year:04d}-12-31" if year >= 0 else str(year)


def parse_year_bounds(value: Any) -> tuple[int | None, int | None]:
    if value is None:
        return None, None

    if isinstance(value, int):
        return value, value

    if not isinstance(value, str):
        return None, None

    value = value.strip()
    if not value:
        return None, None

    match = YEAR_OR_RANGE_RE.match(value)
    if not match:
        return None, None

    start_raw = match.group("start")
    end_raw = match.group("end")

    start = int(start_raw) if start_raw is not None else None

    if "/" not in value:
        return start, start

    if end_raw is None:
        return start, None

    return start, int(end_raw)


def flatten_temporal_metadata(
    data: dict[str, Any],
    *,
    prefix: str = "",
) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(flatten_temporal_metadata(value, prefix=full_key))
            continue
        flat[full_key] = value
        if full_key in TEMPORAL_FIELDS or key in {"date", "created", "issued", "coverage"}:
            start, end = parse_year_bounds(value)
            if start is not None:
                flat[f"{full_key}_start"] = start
                flat[f"{full_key}_start_iso"] = _year_start_iso(start)
            if end is not None:
                flat[f"{full_key}_end"] = end
                flat[f"{full_key}_end_iso"] = _year_end_iso(end)
    return flat


def enrich_temporal_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return flatten_temporal_metadata(metadata)
