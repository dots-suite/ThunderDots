#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Check how ThunderDots reads temporal metadata values.

Two ways to use it:

1. Test values given on the command line (or piped on stdin, one per line)::

       python scripts/check_dates.py -- "-0500/0499" "12XX" "1966-1998" 800

2. Scan the temporal metadata of a live DTS collection and report every value,
   flagging the ones ThunderDots cannot read::

       python scripts/check_dates.py --endpoint https://dots.chartes.psl.eu/api/dts \\
           --collection ENCPOS --depth 1 --only-problems

For each value the script prints the year bounds (``start`` / ``end``) and the ISO
bounds (``start_iso`` / ``end_iso``) that would appear in the temporal index. A value
marked ``UNPARSED`` is kept raw in the output but gets no bounds.

This is a diagnostic tool, not part of the library public API.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from typing import Any, Iterable

from thunderdots.normalize.dates import (
    TEMPORAL_KEYS,
    classify_temporal_value,
    parse_temporal_bounds,
)


def describe(value: Any) -> str:
    """Return a one-line description of how *value* is parsed.

    Three outcomes:

    - ``bounded``: year and ISO bounds are produced;
    - ``UNBOUNDED``: valid EDTF, but no usable year (``XXXX-04-12``), so no bounds;
    - ``UNPARSED``: not understood, the raw value is kept without bounds.
    """
    status = classify_temporal_value(value)
    if status == "unparsed":
        return "UNPARSED  (not EDTF: kept raw, no bounds)"
    if status == "unbounded":
        return "UNBOUNDED (valid EDTF without a year: kept raw, no bounds)"
    start, end, start_iso, end_iso = parse_temporal_bounds(value)
    return f"start={start!s:<7} end={end!s:<7} start_iso={start_iso!s:<14} end_iso={end_iso}"


def check_values(values: Iterable[Any]) -> int:
    """Print the parsing of each value; return the number of unparsed values."""
    problems = 0
    for value in values:
        line = describe(value)
        problems += line.startswith("UNPARSED")
        print(f"{str(value)!r:<24} -> {line}")
    return problems


def _is_temporal_key(key: str) -> bool:
    return key.split(":")[-1] in TEMPORAL_KEYS


def iter_collection_values(endpoint: str, collection_id: str, depth: int, timeout: float):
    """Yield ``(object_id, field, value)`` for every temporal field found in the members
    of *collection_id*, descending *depth* levels into sub-collections."""
    import httpx

    client = httpx.Client(timeout=timeout)
    endpoint = endpoint.rstrip("/")

    def walk(cid: str, level: int):
        response = client.get(f"{endpoint}/collection", params={"id": cid})
        response.raise_for_status()
        data = response.json()
        for member in data.get("member") or []:
            if not isinstance(member, dict):
                continue
            for block in ("dublincore", "dublinCore", "extensions"):
                for key, raw in (member.get(block) or {}).items():
                    if not _is_temporal_key(key):
                        continue
                    for value in raw if isinstance(raw, list) else [raw]:
                        yield member.get("@id"), f"{block}.{key}", value
            if member.get("@type") == "Collection" and level < depth:
                yield from walk(member["@id"], level + 1)

    yield from walk(collection_id, 0)


def check_collection(
    endpoint: str, collection_id: str, depth: int, timeout: float, only_problems: bool
) -> int:
    """Scan a live collection; return the number of unparsed values."""
    total = 0
    problems: Counter[str] = Counter()
    forms: Counter[str] = Counter()

    for object_id, field, value in iter_collection_values(endpoint, collection_id, depth, timeout):
        total += 1
        line = describe(value)
        unparsed = line.startswith("UNPARSED")
        if unparsed:
            problems[f"{object_id} {field}={value!r}"] += 1
        forms["unparsed" if unparsed else "parsed"] += 1
        if unparsed or not only_problems:
            print(f"{object_id:<20} {field:<30} {str(value)!r:<20} -> {line}")

    print()
    print(
        f"{total} temporal values scanned: {forms['parsed']} parsed, {forms['unparsed']} unparsed"
    )
    if problems:
        print("values ThunderDots cannot read (fix the metadata or extend the parser):")
        for item in sorted(problems):
            print(f"  {item}")
    return forms["unparsed"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "values", nargs="*", help="values to test; read from stdin when empty and no --collection"
    )
    parser.add_argument("--endpoint", help="DTS endpoint, e.g. https://dots.chartes.psl.eu/api/dts")
    parser.add_argument("--collection", help="collection or resource identifier to scan")
    parser.add_argument(
        "--depth", type=int, default=1, help="sub-collection levels to descend (default: 1)"
    )
    parser.add_argument("--timeout", type=float, default=120.0, help="HTTP timeout in seconds")
    parser.add_argument("--only-problems", action="store_true", help="print unparsed values only")
    args = parser.parse_args(argv)

    if args.collection:
        if not args.endpoint:
            parser.error("--collection requires --endpoint")
        problems = check_collection(
            args.endpoint, args.collection, args.depth, args.timeout, args.only_problems
        )
    else:
        values: list[Any] = list(args.values)
        if not values and not sys.stdin.isatty():
            values = [line.rstrip("\n") for line in sys.stdin if line.strip()]
        if not values:
            parser.error("give values to test, pipe them on stdin, or use --endpoint/--collection")
        problems = check_values(values)

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
