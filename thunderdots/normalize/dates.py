# -*- coding: utf-8 -*-

"""dates.py

Functions for parsing and normalizing temporal metadata fields, especially those containing years or year ranges.
"""

from __future__ import annotations

import calendar
import re
from typing import Any


# One EDTF date (level 0 and the level 1 features below), without the interval part:
#   - year: signed 4-digit year in astronomical numbering (``0499``, ``-0500``, ``0000`` = 1 BC);
#     years with fewer digits (``800``, ``-50``) are tolerated and read as the padded year;
#   - ``Y`` prefix for years beyond 4 digits (``Y-12000``, ``Y170000002``);
#   - unspecified digits in the year (``12XX`` = 1200 to 1299) and ``XX`` month or day;
#   - optional month and day (``1157-03``, ``1157-03-04``).
# Qualifiers ``?`` (uncertain), ``~`` (approximate) and ``%`` (both) are removed before
# matching, wherever EDTF allows them: after the date (level 1, ``1984?``), after a
# component (level 2, ``2004-06~-11``) or before one (level 2, ``~1455``, ``?2004-06-~11``).
# They never change the bounds.
_PART_RE = re.compile(
    r"^(?:Y(?P<long>[+-]?\d{5,})"
    r"|(?P<year>[+-]?(?:\d{1,4}|\d{3}X|\d{2}XX|\dXXX|XXXX))"
    r"(?:-(?P<month>\d{2}|XX)(?:-(?P<day>\d{2}|XX))?)?)$",
    re.IGNORECASE,
)

_QUALIFIERS_RE = re.compile(r"[?~%]")

# (start_year, end_year, start_iso, end_iso)
TemporalBounds = tuple[int | None, int | None, str | None, str | None]

_NO_BOUNDS: TemporalBounds = (None, None, None, None)


def _clean_part(part: str | None) -> str:
    """Strip whitespace and EDTF qualifiers from one date part."""
    return _QUALIFIERS_RE.sub("", (part or "").strip())


def _part_syntax_ok(part: str | None) -> bool:
    """Return True when a part is empty, an open bound, or a syntactically valid EDTF date
    (even one without a usable year, such as ``XXXX-04-12``)."""
    cleaned = _clean_part(part)
    return cleaned in ("", "..") or _PART_RE.match(cleaned) is not None


def _iso_year(year: int) -> str:
    """Format a year the ISO 8601 / EDTF way: four digits, a leading minus sign for years
    before year 0, and an explicit ``+`` sign for years beyond four digits.

    :param year: Astronomical year number (``0`` is 1 BC, ``-1`` is 2 BC).
    :type year: int
    :return: ``0499``, ``-0500``, ``+12000``.
    :rtype: str
    """
    if year < 0:
        return f"-{-year:04d}"
    if year > 9999:
        return f"+{year}"
    return f"{year:04d}"


def _days_in_month(year: int, month: int) -> int:
    """Return the length of a month in the proleptic Gregorian calendar, for any year.

    ``calendar.monthrange`` refuses years before 1; ``calendar.isleap`` works for any
    integer and follows astronomical numbering (year 0 is a leap year).

    :param year: Astronomical year number.
    :type year: int
    :param month: Month number, 1 to 12.
    :type month: int
    :return: Number of days.
    :rtype: int
    """
    if month == 2:
        return 29 if calendar.isleap(year) else 28
    return 30 if month in (4, 6, 9, 11) else 31


def _year_start_iso(year: int) -> str:
    """ISO date of the first day of a year (``-0500-01-01`` for year -500)."""
    return f"{_iso_year(year)}-01-01"


def _year_end_iso(year: int) -> str:
    """ISO date of the last day of a year (``-0500-12-31`` for year -500)."""
    return f"{_iso_year(year)}-12-31"


def _bounds_of_part(part: str | None) -> TemporalBounds:
    """Return the years and ISO bounds covered by one EDTF date (no interval).

    The precision of the value is kept in the ISO bounds:

    - ``1200`` covers ``1200-01-01`` to ``1200-12-31``;
    - ``1200-09`` covers ``1200-09-01`` to ``1200-09-30``;
    - ``1200-09-15`` covers that single day;
    - ``12XX`` covers ``1200-01-01`` to ``1299-12-31`` (its year bounds differ);
    - ``-0050-01-01`` covers that day of year -50 (51 BC).

    An out-of-range month or day falls back to the coarser precision. An empty part or
    ``..`` (open or unknown bound) yields no bounds at all.

    :param part: One side of an EDTF value, possibly with qualifiers.
    :type part: str | None
    :return: ``(start_year, end_year, start_iso, end_iso)``, all None when unparsable.
    :rtype: TemporalBounds
    """
    part = _clean_part(part)
    if part in ("", ".."):
        return _NO_BOUNDS

    match = _PART_RE.match(part)
    if not match:
        return _NO_BOUNDS

    if match.group("long"):
        year = int(match.group("long"))
        return year, year, _year_start_iso(year), _year_end_iso(year)

    raw_year = match.group("year")
    sign = -1 if raw_year.startswith("-") else 1
    digits = raw_year.lstrip("+-").upper()

    if "X" in digits:
        known = digits.rstrip("X")
        if not known:
            # ``XXXX``: the year is entirely unspecified, nothing usable.
            return _NO_BOUNDS
        unspecified = len(digits) - len(known)
        first = sign * int(known + "0" * unspecified)
        last = sign * int(known + "9" * unspecified)
        low, high = min(first, last), max(first, last)
        return low, high, _year_start_iso(low), _year_end_iso(high)

    year = sign * int(digits)

    month = match.group("month")
    if month is None or month.upper() == "XX" or not 1 <= int(month) <= 12:
        return year, year, _year_start_iso(year), _year_end_iso(year)
    month = int(month)

    last_day = _days_in_month(year, month)
    day = match.group("day")
    if day is None or day.upper() == "XX" or not 1 <= int(day) <= last_day:
        prefix = f"{_iso_year(year)}-{month:02d}"
        return year, year, f"{prefix}-01", f"{prefix}-{last_day:02d}"

    iso = f"{_iso_year(year)}-{month:02d}-{int(day):02d}"
    return year, year, iso, iso


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


def parse_temporal_bounds(value: Any) -> TemporalBounds:
    """Parse an EDTF date or interval into year and ISO bounds.

    Supported values: integer years; EDTF level 0 dates (``1157``, ``-0500``,
    ``1157-03``, ``1157-03-04``); the level 1 features ``Y`` long years, unspecified
    digits (``12XX``, ``1157-XX``) and ``?`` ``~`` ``%`` qualifiers, also in the level 2
    positions (``~1455``, ``2004-06~-11``); intervals with ``/`` (``1200/1499``,
    ``1157-03/1158-01``), including open or unknown ends (``1180/``, ``../1250``); level
    2 sets ``[1667,1668,1670..1672]`` and ``{1667,1668}``, reduced to their overall span.
    Years with fewer than four digits (``800``, ``-50``) are tolerated.

    The year bounds are integers in astronomical numbering. The ISO bounds keep the
    precision of the value: ``1200-09`` gives ``1200-09-01`` / ``1200-09-30``, ``1200``
    gives ``1200-01-01`` / ``1200-12-31``, ``-0500`` gives ``-0500-01-01`` /
    ``-0500-12-31``.

    Anything else (``1966-1998``, ``circa 1200``) is left unparsed. A valid date whose
    year is entirely unspecified (``XXXX-11-21``) has no computable bounds either; see
    :func:`classify_temporal_value` to tell the two cases apart.

    :param value: Value to parse.
    :type value: Any
    :return: Tuple ``(start_year, end_year, start_iso, end_iso)``; all None when the
        value cannot be parsed.
    :rtype: TemporalBounds
    """
    if value is None or isinstance(value, bool):
        return _NO_BOUNDS

    if isinstance(value, int):
        return _bounds_of_part(str(value))

    if not isinstance(value, str):
        return _NO_BOUNDS

    value = value.strip()
    if not value:
        return _NO_BOUNDS

    if value[0] in "[{" and value[-1] in "]}":
        return _bounds_of_set(value[1:-1])

    return _bounds_of_interval(value)


def _bounds_of_interval(value: str) -> TemporalBounds:
    """Bounds of one EDTF date or ``start/end`` interval."""
    if "/" not in value:
        return _bounds_of_part(value)

    start_raw, _, end_raw = value.partition("/")
    if "/" in end_raw:
        return _NO_BOUNDS

    # A side that is not valid EDTF invalidates the whole value: the raw string is then
    # kept as is, without bounds, rather than half-interpreted (``abc/1250``). A side that
    # is valid but carries no usable year (``XXXX-04-12/1899``) behaves like an open bound.
    if not (_part_syntax_ok(start_raw) and _part_syntax_ok(end_raw)):
        return _NO_BOUNDS

    start = _bounds_of_part(start_raw)
    end = _bounds_of_part(end_raw)

    if start is _NO_BOUNDS and end is _NO_BOUNDS:
        return _NO_BOUNDS

    return start[0], end[1], start[2], end[3]


def _bounds_of_set(inner: str) -> TemporalBounds:
    """Bounds of an EDTF level 2 set, ``[...]`` (one of) or ``{...}`` (all of), reduced to
    the span from its earliest to its latest member. Members are dates or ``a..b``
    ranges, possibly open (``..1670``, ``1670..``)."""
    members = [item.strip() for item in inner.split(",") if item.strip()]
    if not members:
        return _NO_BOUNDS

    starts: list[tuple[int, str]] = []
    ends: list[tuple[int, str]] = []
    open_start = open_end = False

    for member in members:
        if ".." in member:
            first, _, last = member.partition("..")
            if not (_part_syntax_ok(first) and _part_syntax_ok(last)):
                return _NO_BOUNDS
            bounds = _bounds_of_interval(f"{first}/{last}")
            open_start |= not first.strip()
            open_end |= not last.strip()
        else:
            if not _part_syntax_ok(member):
                return _NO_BOUNDS
            bounds = _bounds_of_part(member)

        # A valid member without a usable year (``XXXX-04``) simply adds no bound.
        if bounds[0] is not None:
            starts.append((bounds[0], bounds[2]))
        if bounds[1] is not None:
            ends.append((bounds[1], bounds[3]))

    start = None if open_start or not starts else min(starts)
    end = None if open_end or not ends else max(ends)
    if start is None and end is None:
        return _NO_BOUNDS

    return (
        start[0] if start else None,
        end[0] if end else None,
        start[1] if start else None,
        end[1] if end else None,
    )


def classify_temporal_value(value: Any) -> str:
    """Tell how ThunderDots handles a temporal value.

    :param value: Value to classify.
    :type value: Any
    :return: ``"bounded"`` when year bounds are computed; ``"unbounded"`` when the value is
        syntactically valid EDTF but carries no usable year (``XXXX-04-12``, ``..``);
        ``"unparsed"`` when the value is not understood and is kept raw.
    :rtype: str
    """
    if parse_temporal_bounds(value) != _NO_BOUNDS:
        return "bounded"

    if isinstance(value, bool) or not isinstance(value, str):
        return "unparsed"

    text = value.strip()
    if text[:1] in "[{" and text[-1:] in "]}":
        members = [m.strip() for m in text[1:-1].split(",") if m.strip()]
        parts = [p for m in members for p in (m.split("..") if ".." in m else [m])]
    else:
        parts = text.split("/")
        if len(parts) > 2:
            return "unparsed"

    if parts and all(_part_syntax_ok(p) for p in parts):
        return "unbounded"
    return "unparsed"


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
    # Namespaced keys such as ``dct:coverage`` or ``schema:dateCreated`` are matched on
    # their local name, so that Dublin Core terms in ``extensions`` are indexed too.
    local = key.rsplit(":", 1)[-1]
    return full_key in TEMPORAL_FIELDS or key in TEMPORAL_KEYS or local in TEMPORAL_KEYS


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
