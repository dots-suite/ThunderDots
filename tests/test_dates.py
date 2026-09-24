from __future__ import annotations

import pytest

from thunderdots.normalize.dates import (
    classify_temporal_value,
    enrich_temporal_metadata,
    parse_temporal_bounds,
    parse_year_bounds,
)

NONE = (None, None, None, None)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        # EDTF level 0: years, months, days, in astronomical numbering.
        ("1200", (1200, 1200, "1200-01-01", "1200-12-31")),
        ("0499", (499, 499, "0499-01-01", "0499-12-31")),
        ("0000", (0, 0, "0000-01-01", "0000-12-31")),
        ("-0500", (-500, -500, "-0500-01-01", "-0500-12-31")),
        ("-0050-01-01", (-50, -50, "-0050-01-01", "-0050-01-01")),
        ("-0050-02", (-50, -50, "-0050-02-01", "-0050-02-28")),
        ("-0004-02", (-4, -4, "-0004-02-01", "-0004-02-29")),
        ("1173-05-02", (1173, 1173, "1173-05-02", "1173-05-02")),
        # Reported ENCPOS values (all valid EDTF).
        ("-0500/0499", (-500, 499, "-0500-01-01", "0499-12-31")),
        ("-0103/1700", (-103, 1700, "-0103-01-01", "1700-12-31")),
        ("-0283/0877", (-283, 877, "-0283-01-01", "0877-12-31")),
        ("-0199/0100", (-199, 100, "-0199-01-01", "0100-12-31")),
        # Tolerated: years without zero padding (not strict EDTF, common in the corpora).
        ("800/1875", (800, 1875, "0800-01-01", "1875-12-31")),
        ("-500/1499", (-500, 1499, "-0500-01-01", "1499-12-31")),
        ("50", (50, 50, "0050-01-01", "0050-12-31")),
        (-50, (-50, -50, "-0050-01-01", "-0050-12-31")),
        # EDTF level 1: qualifiers, long years, unspecified digits, open/unknown ends.
        ("0975~/1280", (975, 1280, "0975-01-01", "1280-12-31")),
        ("1200?/1250-10~", (1200, 1250, "1200-01-01", "1250-10-31")),
        ("1984%", (1984, 1984, "1984-01-01", "1984-12-31")),
        ("Y-12000", (-12000, -12000, "-12000-01-01", "-12000-12-31")),
        ("Y170000002", (170000002, 170000002, "+170000002-01-01", "+170000002-12-31")),
        ("12XX", (1200, 1299, "1200-01-01", "1299-12-31")),
        ("-1XXX", (-1999, -1000, "-1999-01-01", "-1000-12-31")),
        ("1157-XX", (1157, 1157, "1157-01-01", "1157-12-31")),
        ("1157-03-XX", (1157, 1157, "1157-03-01", "1157-03-31")),
        ("../1250", (None, 1250, None, "1250-12-31")),
        ("1250/..", (1250, None, "1250-01-01", None)),
        ("1180/", (1180, None, "1180-01-01", None)),
        # EDTF level 2: qualifiers before a component or between components.
        ("~1455", (1455, 1455, "1455-01-01", "1455-12-31")),
        ("~400", (400, 400, "0400-01-01", "0400-12-31")),
        ("~0400", (400, 400, "0400-01-01", "0400-12-31")),
        ("~1899?", (1899, 1899, "1899-01-01", "1899-12-31")),
        ("?2004-06-~11", (2004, 2004, "2004-06-11", "2004-06-11")),
        ("2004-06~-11", (2004, 2004, "2004-06-11", "2004-06-11")),
        ("~1455/~1460", (1455, 1460, "1455-01-01", "1460-12-31")),
        # EDTF level 2: sets, reduced to their overall span.
        ("[1667,1668,1670..1672]", (1667, 1672, "1667-01-01", "1672-12-31")),
        ("{1667,1668}", (1667, 1668, "1667-01-01", "1668-12-31")),
        ("[1667-03,1667-01-15]", (1667, 1667, "1667-01-15", "1667-03-31")),
        ("[..1670,1680]", (None, 1680, None, "1680-12-31")),
        ("[1670..]", (1670, None, "1670-01-01", None)),
        ("[1667,abc]", NONE),
        ("[]", NONE),
        # A valid side without a usable year behaves like an open bound.
        ("XXXX-04-12/1899-06-20", (None, 1899, None, "1899-06-20")),
        ("1850/XXXX-06", (1850, None, "1850-01-01", None)),
        ("[XXXX-04,1670..1672]", (1670, 1672, "1670-01-01", "1672-12-31")),
        ("XXXX-04-12/XXXX-12-12", NONE),
        # Precision fallbacks.
        ("1200-13", (1200, 1200, "1200-01-01", "1200-12-31")),
        ("1200-09-31", (1200, 1200, "1200-09-01", "1200-09-30")),
        # Year 0 is 1 BC and exists in astronomical numbering.
        ("0000-04-12", (0, 0, "0000-04-12", "0000-04-12")),
        # Not parsed: raw value is kept by the enrichment, no bounds produced.
        ("XXXX-11-21", NONE),
        ("XXXX-04-12", NONE),
        ("1966-1998", NONE),
        ("circa 1200", NONE),
        ("12 septembre 1399", NONE),
        ("XIVe siècle", NONE),
        ("abc/1250", NONE),
        ("1200/1250/1300", NONE),
        ("", NONE),
        (None, NONE),
        (True, NONE),
        (12.5, NONE),
    ],
)
def test_parse_temporal_bounds(value, expected) -> None:
    """Verify EDTF parsing, including negative years and level 1 features."""
    assert parse_temporal_bounds(value) == expected


def test_parse_year_bounds_matches_temporal_bounds() -> None:
    assert parse_year_bounds("-0500/0499") == (-500, 499)
    assert parse_year_bounds("12XX") == (1200, 1299)
    assert parse_year_bounds("1966-1998") == (None, None)


def test_negative_years_produce_real_iso_dates_in_temporal_index() -> None:
    """Regression: a bare '-50' bound was read by Elasticsearch as epoch milliseconds."""
    temporal = enrich_temporal_metadata({"extensions": {"dct:coverage": "-0500/0499"}})

    assert temporal["extensions.dct:coverage_start"] == -500
    assert temporal["extensions.dct:coverage_end"] == 499
    assert temporal["extensions.dct:coverage_start_iso"] == "-0500-01-01"
    assert temporal["extensions.dct:coverage_end_iso"] == "0499-12-31"
    # Every ISO bound is a full calendar date, never a bare number.
    for key in ("extensions.dct:coverage_start_iso", "extensions.dct:coverage_end_iso"):
        assert temporal[key].count("-") >= 2 and len(temporal[key].lstrip("-")) == 10


def test_unparsed_values_keep_raw_value_without_bounds() -> None:
    temporal = enrich_temporal_metadata({"dublincore": {"created": "1966-1998"}})

    assert temporal == {"dublincore.created": "1966-1998"}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1455", "bounded"),
        ("~1455", "bounded"),
        ("-0500/0499", "bounded"),
        ("[1667,1670..1672]", "bounded"),
        (1455, "bounded"),
        # Valid EDTF, but no year to build bounds from.
        ("XXXX-04-12", "unbounded"),
        ("XXXX", "unbounded"),
        ("XXXX-04-12/XXXX-05", "unbounded"),
        ("XXXX-04-12/1899-06-20", "bounded"),
        ("abc/1899-06-20", "unparsed"),
        ("[XXXX-04,XXXX-05]", "unbounded"),
        ("..", "unbounded"),
        # Not EDTF at all.
        ("12 septembre 1399", "unparsed"),
        ("XIVe siècle", "unparsed"),
        ("1966-1998", "unparsed"),
        ("1200/1250/1300", "unparsed"),
        ("", "unparsed"),
        (None, "unparsed"),
        (12.5, "unparsed"),
    ],
)
def test_classify_temporal_value(value, expected) -> None:
    """Verify the three-way classification used by scripts/check_dates.py."""
    assert classify_temporal_value(value) == expected
