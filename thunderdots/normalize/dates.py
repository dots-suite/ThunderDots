# -*- coding: utf-8 -*-

"""dates.py

Functions for parsing and normalizing temporal metadata fields, especially those containing years or year ranges.
"""

from __future__ import annotations

import calendar
import re
from typing import Any


# A year (``1157``, ``-50``), optionally followed by an ISO month/day (``1157-03``,
# ``1157-03-04``) and an EDTF approximation marker, or a ``start/end`` range of those.
_YEAR_PART = r"-?\d{1,4}(?:-\d{2}(?:-\d{2})?)?"

YEAR_OR_RANGE_RE = re.compile(
    rf"^\s*(?P<start>{_YEAR_PART})(?P<start_approx>[~?])?"
    rf"(?:/(?P<end>{_YEAR_PART})?(?P<end_approx>[~?])?)?\s*$"
)

# (start_year, end_year, start_iso, end_iso)
TemporalBounds = tuple[int | None, int | None, str | None, str | None]


def _bounds_of_part(part: str | None) -> tuple[int | None, str | None, str | None]:
    """Return the year and the ISO bounds covered by one ``YYYY``, ``YYYY-MM`` or
    ``YYYY-MM-DD`` date part, keeping its precision.

    - ``1200`` covers ``1200-01-01`` to ``1200-12-31``;
    - ``1200-09`` covers ``1200-09-01`` to ``1200-09-30``;
    - ``1200-09-15`` covers that single day.

    An out-of-range month or day falls back to the coarser precision. Years before 1 are
    returned as plain year strings, since ISO calendar dates are not defined for them here.

    :param part: Matched date part, possibly with a leading minus sign.
    :type part: str | None
    :return: Tuple ``(year, start_iso, end_iso)``, all None when *part* is empty.
    :rtype: tuple[int | None, str | None, str | None]
    """
    if not part:
        return None, None, None

    negative = part.startswith("-")
    pieces = part.lstrip("-").split("-")
    year = -int(pieces[0]) if negative else int(pieces[0])

    if year < 1:
        return year, str(year), str(year)

    month = int(pieces[1]) if len(pieces) > 1 else None
    if month is None or not 1 <= month <= 12:
        return year, _year_start_iso(year), _year_end_iso(year)

    last_day = calendar.monthrange(year, month)[1]
    day = int(pieces[2]) if len(pieces) > 2 else None
    if day is None or not 1 <= day <= last_day:
        return year, f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last_day:02d}"

    iso = f"{year:04d}-{month:02d}-{day:02d}"
    return year, iso, iso


TEMPORAL_FIELDS = {
    "dublincore.date",
    "dublincore.created",
    "dublincore.issued",
    "dublincore.coverage",
    "extensions.dateCreated",
    "extensions.datePublished",
    "extensions.temporalCoverage",
}


TEMPORAL_KEYS = {
    "date",
    "created",
    "issued",
    "coverage",
    "temporal",
    "temporalCoverage",
    "dateCreated",
    "datePublished",
}


def _year_start_iso(year: int) -> str:
    """Convert a year to an ISO date string representing the start of that year.

    :param year: Year to convert.
    :type year: int
    :return: ISO date string representing the first day of the year.
    :rtype: str
    """
    return f"{year:04d}-01-01" if year >= 0 else str(year)


def _year_end_iso(year: int) -> str:
    """Convert a year to an ISO date string representing the end of that year.

    :param year: Year to convert.
    :type year: int
    :return: ISO date string representing the last day of the year.
    :rtype: str
    """
    return f"{year:04d}-12-31" if year >= 0 else str(year)


def parse_temporal_bounds(value: Any) -> TemporalBounds:
    """Parse a date, a year, or a range of those into year and ISO bounds.

    Supported values include integer years, string years, ISO dates (``1157-03``,
    ``1157-03-04``), EDTF approximation markers (``1200?``, ``1250~``) and simple
    ranges such as ``1200/1499``, ``1157-03/1158-01`` or ``1180/`` (open end).

    The year bounds are integers. The ISO bounds keep the precision of the value:
    ``1200-09`` gives ``1200-09-01`` / ``1200-09-30`` and ``1200`` gives
    ``1200-01-01`` / ``1200-12-31``.

    :param value: Value to parse.
    :type value: Any
    :return: Tuple ``(start_year, end_year, start_iso, end_iso)``; all None when the
        value cannot be parsed.
    :rtype: TemporalBounds
    """
    if value is None:
        return None, None, None, None

    if isinstance(value, bool):
        return None, None, None, None

    if isinstance(value, int):
        _, start_iso, end_iso = _bounds_of_part(str(value))
        return value, value, start_iso, end_iso

    if not isinstance(value, str):
        return None, None, None, None

    value = value.strip()
    if not value:
        return None, None, None, None

    match = YEAR_OR_RANGE_RE.match(value)
    if not match:
        return None, None, None, None

    start_year, start_iso, start_end_iso = _bounds_of_part(match.group("start"))

    if "/" not in value:
        return start_year, start_year, start_iso, start_end_iso

    end_year, _, end_iso = _bounds_of_part(match.group("end"))
    return start_year, end_year, start_iso, end_iso


def parse_year_bounds(value: Any) -> tuple[int | None, int | None]:
    """Parse a year or year range from a value.

    Supported values include integer years, string years, ISO dates reduced to
    their year (``1157-03-04``), and simple ranges such as ``1200/1499`` or
    ``1157-03/1158-01``. See :func:`parse_temporal_bounds` for ISO bounds.

    :param value: Value to parse.
    :type value: Any
    :return: Tuple containing start and end years when available.
    :rtype: tuple[int | None, int | None]
    """
    start_year, end_year, _, _ = parse_temporal_bounds(value)
    return start_year, end_year


def _is_temporal_field(full_key: str, key: str) -> bool:
    """Return True when a metadata field should be treated as temporal.

    :param full_key: Full dotted metadata path.
    :type full_key: str
    :param key: Local metadata key.
    :type key: str
    :return: True if the field is temporal, False otherwise.
    :rtype: bool
    """
    return full_key in TEMPORAL_FIELDS or key in TEMPORAL_KEYS


def flatten_temporal_metadata(
    data: dict[str, Any],
    *,
    prefix: str = "",
    include_unparsed_temporal_values: bool = True,
) -> dict[str, Any]:
    """Extract temporal metadata from a nested metadata dictionary.

    This function walks through a nested metadata dictionary and returns only
    temporal fields. For each temporal value that can be parsed as a date, a year
    or a range, it adds ``_start`` and ``_end`` (years) plus ``_start_iso`` and
    ``_end_iso`` (ISO dates keeping the precision of the value: ``1200-09`` gives
    ``1200-09-01`` / ``1200-09-30``).

    Non-temporal metadata fields are ignored.

    :param data: Nested metadata dictionary to inspect.
    :type data: dict[str, Any]
    :param prefix: Dotted path prefix used during recursion.
    :type prefix: str
    :param include_unparsed_temporal_values: Whether to keep temporal fields even when their values cannot be parsed as years.
    :type include_unparsed_temporal_values: bool
    :return: Dictionary containing only temporal metadata and parsed date bounds.
    :rtype: dict[str, Any]
    """
    temporal: dict[str, Any] = {}

    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key

        if isinstance(value, dict):
            temporal.update(
                flatten_temporal_metadata(
                    value,
                    prefix=full_key,
                    include_unparsed_temporal_values=include_unparsed_temporal_values,
                )
            )
            continue

        if not _is_temporal_field(full_key, key):
            continue

        start, end, start_iso, end_iso = parse_temporal_bounds(value)

        if start is None and end is None:
            if include_unparsed_temporal_values:
                temporal[full_key] = value
            continue

        temporal[full_key] = value

        if start is not None:
            temporal[f"{full_key}_start"] = start
            temporal[f"{full_key}_start_iso"] = start_iso

        if end is not None:
            temporal[f"{full_key}_end"] = end
            temporal[f"{full_key}_end_iso"] = end_iso

    return temporal


def enrich_temporal_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Return temporal metadata enriched with parsed year bounds.

    Only temporal fields are returned. General descriptive metadata such as
    creators, publishers, titles, identifiers, and source records are excluded.

    :param metadata: Nested metadata dictionary to enrich.
    :type metadata: dict[str, Any]
    :return: Dictionary containing temporal metadata only.
    :rtype: dict[str, Any]
    """
    return flatten_temporal_metadata(metadata)
