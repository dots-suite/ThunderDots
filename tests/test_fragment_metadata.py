from __future__ import annotations

import pytest

from conftest import load_json, load_xml
from thunderdots import ThunderDots
from thunderdots.config import FragmentsParams
from thunderdots.extract.resources import attach_fragment_temporal_index
from thunderdots.extract.tei import (
    extract_document_text_fast,
    extract_fragments,
    extract_fragments_by_xpath,
)
from thunderdots.normalize.dates import (
    enrich_temporal_metadata,
    parse_temporal_bounds,
    parse_year_bounds,
)
from thunderdots.orm import Fragment, stable_int_id
from thunderdots.validation import validate_many

DOCDATE_XPATH = ".//tei:docDate/tei:date"


def _by_id(fragments: list[dict]) -> dict[str, dict]:
    return {fragment["id"]: fragment for fragment in fragments}


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #


def test_fragment_params_from_dict_parses_all_fields() -> None:
    """Verify that fragment parameters expose Dublin Core, extensions, temporal options."""
    params = FragmentsParams.from_dict(
        {
            "metadata_dublincore": ["title"],
            "metadata_extensions": ["name"],
            "temporal_index": "AUTO",
            "temporal_xpath": f"  {DOCDATE_XPATH}  ",
        }
    )

    assert params.metadata_dublincore == ["title"]
    assert params.metadata_extensions == ["name"]
    assert params.temporal_index == "auto"
    assert params.temporal_xpath == DOCDATE_XPATH
    assert params.requested is True

    defaults = FragmentsParams.from_dict(None)
    assert defaults.metadata_dublincore is None
    assert defaults.metadata_extensions is None
    assert defaults.temporal_xpath is None
    assert defaults.requested is False


@pytest.mark.parametrize("value", ["yes", 1, None])
def test_fragment_params_reject_invalid_temporal_index(value) -> None:
    """Verify that temporal_index only accepts booleans or 'auto'."""
    with pytest.raises(ValueError):
        FragmentsParams.from_dict({"temporal_index": value})


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        (None, False),
        ({}, False),
        ({"metadata_dublincore": None, "metadata_extensions": None}, True),
        ({"metadata_dublincore": None}, True),
        ({"metadata_extensions": ["name"]}, True),
        ({"metadata_dublincore": [], "metadata_extensions": []}, False),
        ({"metadata_dublincore": [], "metadata_extensions": [], "temporal_xpath": "."}, True),
        ({"temporal_xpath": DOCDATE_XPATH}, True),
        ({"temporal_index": True}, True),
        ({"temporal_index": False, "metadata_dublincore": None}, False),
    ],
)
def test_fragment_params_temporal_index_auto_resolution(params, expected) -> None:
    """Verify that 'auto' enables the fragment temporal index only on explicit request."""
    assert FragmentsParams.from_dict(params).temporal_index_enabled is expected


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #


def test_navigation_mode_accepts_both_dublincore_spellings() -> None:
    """Verify that fragment metadata is read from 'dublinCore' as well as 'dublincore' members."""
    camel = _by_id(
        extract_fragments(
            load_json("navigation_cartulaire_sample.json"),
            load_xml("cartulaire_sample.xml"),
        )
    )
    lower = _by_id(
        extract_fragments(
            load_json("navigation_encpos_2025_01.json"),
            load_xml("encpos_1893_05.xml"),
        )
    )

    assert camel["CART_SAMPLE_0001"]["metadata"]["dublincore"]["title"] == "Donation de Louis VII."
    assert camel["CART_SAMPLE_0001"]["metadata"]["extensions"]["inLanguage"] == "lat"
    assert lower["intro"]["metadata"]["dublincore"]["title"] == "Introduction"

    # Legacy alias mirrors the Dublin Core block.
    assert (
        camel["CART_SAMPLE_0001"]["metadata_dublincore"]
        == (camel["CART_SAMPLE_0001"]["metadata"]["dublincore"])
    )


def test_navigation_mode_filters_fragment_metadata() -> None:
    """Verify that fragment metadata filters follow the None / [] / list semantics."""
    nav = load_json("navigation_cartulaire_sample.json")
    xml = load_xml("cartulaire_sample.xml")

    filtered = _by_id(
        extract_fragments(
            nav,
            xml,
            fragment_metadata_dublincore_params=["title"],
            fragment_metadata_extensions_params=["name"],
        )
    )
    act = filtered["CART_SAMPLE_0001"]["metadata"]
    assert act == {
        "dublincore": {"title": "Donation de Louis VII."},
        "extensions": {"name": "Donation de Louis VII."},
    }

    none_kept = _by_id(
        extract_fragments(
            nav,
            xml,
            fragment_metadata_dublincore_params=[],
            fragment_metadata_extensions_params=[],
        )
    )
    assert none_kept["CART_SAMPLE_0001"]["metadata"] == {}
    assert none_kept["CART_SAMPLE_0001"]["metadata_dublincore"] is None


def test_temporal_xpath_reads_tei_dates_and_ignores_descendant_fragments() -> None:
    """Verify TEI date extraction (text, @when, @notBefore/@notAfter) scoped to each fragment."""
    fragments = _by_id(
        extract_fragments(
            load_json("navigation_cartulaire_sample.json"),
            load_xml("cartulaire_sample.xml"),
            temporal_xpath=DOCDATE_XPATH,
        )
    )

    assert fragments["CART_SAMPLE_0001"]["metadata"]["tei"] == {"date": "1157"}
    assert fragments["CART_SAMPLE_0002"]["metadata"]["tei"] == {"date": "1173-05-02"}
    assert fragments["CART_SAMPLE_0003"]["metadata"]["tei"] == {"date": "1180/1185"}

    # The container group must not take over the dates of the acts it contains.
    assert "tei" not in fragments["CART_SAMPLE_group"]["metadata"]
    assert "tei" not in fragments["CART_SAMPLE_front"]["metadata"]
    assert "tei" not in fragments["CART_SAMPLE_notice"]["metadata"]


def test_attach_fragment_temporal_index_uses_only_fragment_metadata() -> None:
    """Verify that the fragment temporal index is derived from the fragment's own metadata."""
    fragments = extract_fragments(
        load_json("navigation_cartulaire_sample.json"),
        load_xml("cartulaire_sample.xml"),
        temporal_xpath=DOCDATE_XPATH,
    )
    attach_fragment_temporal_index(fragments)
    by_id = _by_id(fragments)

    assert by_id["CART_SAMPLE_0001"]["temporal"]["tei.date_start"] == 1157
    assert by_id["CART_SAMPLE_0001"]["temporal"]["tei.date_end_iso"] == "1157-12-31"

    second = by_id["CART_SAMPLE_0002"]["temporal"]
    assert second["dublincore.date_start"] == 1173
    assert second["dublincore.date_start_iso"] == "1173-05-02"
    assert second["dublincore.date_end_iso"] == "1173-05-02"
    assert second["tei.date_start"] == 1173
    assert second["tei.date_end_iso"] == "1173-05-02"

    third = by_id["CART_SAMPLE_0003"]["temporal"]
    assert third["extensions.temporalCoverage_start"] == 1180
    assert third["extensions.temporalCoverage_end"] == 1185
    assert third["tei.date_start"] == 1180
    assert third["tei.date_end"] == 1185

    # No explicit date: empty index, nothing inherited.
    assert by_id["CART_SAMPLE_notice"]["temporal"] == {}
    assert by_id["CART_SAMPLE_group"]["temporal"] == {}


def test_xpath_mode_supports_temporal_xpath() -> None:
    """Verify that TEI XPath mode evaluates temporal_xpath relative to each selected node."""
    fragments = _by_id(
        extract_fragments_by_xpath(
            load_xml("cartulaire_sample.xml"),
            fragment_xpath=".//tei:group/tei:text",
            title_xpath="./tei:front/tei:head",
            temporal_xpath=DOCDATE_XPATH,
        )
    )

    assert set(fragments) == {"CART_SAMPLE_0001", "CART_SAMPLE_0002", "CART_SAMPLE_0003"}
    assert fragments["CART_SAMPLE_0002"]["metadata"] == {"tei": {"date": "1173-05-02"}}
    assert fragments["CART_SAMPLE_0002"]["head"] == "Sentence arbitrale."


def test_document_mode_exposes_metadata_block() -> None:
    """Verify that document mode always exposes a metadata block, filled by temporal_xpath."""
    xml = load_xml("cartulaire_sample.xml")

    plain = extract_document_text_fast(xml)
    assert plain[0]["metadata"] == {}

    dated = extract_document_text_fast(xml, temporal_xpath=DOCDATE_XPATH)
    assert dated[0]["metadata"]["tei"]["date"] == "1157"
    assert dated[0]["metadata"]["tei"]["dates"] == ["1157", "1173-05-02", "1180/1185"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1157", (1157, 1157)),
        ("1157-03-04", (1157, 1157)),
        ("1173-05", (1173, 1173)),
        ("1180/1185", (1180, 1185)),
        ("1157-03/1158-01-01", (1157, 1158)),
        ("1180/", (1180, None)),
        ("-50/-20", (-50, -20)),
        ("1200?/1250~", (1200, 1250)),
        ("1966-1998", (None, None)),
        ("circa 1200", (None, None)),
    ],
)
def test_parse_year_bounds_accepts_iso_dates(value, expected) -> None:
    """Verify that ISO dates are reduced to their year while non-EDTF ranges stay unparsed."""
    assert parse_year_bounds(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1200", (1200, 1200, "1200-01-01", "1200-12-31")),
        (1200, (1200, 1200, "1200-01-01", "1200-12-31")),
        ("1200-09", (1200, 1200, "1200-09-01", "1200-09-30")),
        ("1200-02", (1200, 1200, "1200-02-01", "1200-02-29")),
        ("1173-05-02", (1173, 1173, "1173-05-02", "1173-05-02")),
        ("1157-03/1158-01", (1157, 1158, "1157-03-01", "1158-01-31")),
        ("1180/1185", (1180, 1185, "1180-01-01", "1185-12-31")),
        ("1180-06/", (1180, None, "1180-06-01", None)),
        ("1200?/1250-10~", (1200, 1250, "1200-01-01", "1250-10-31")),
        ("1200-13", (1200, 1200, "1200-01-01", "1200-12-31")),
        ("1200-09-31", (1200, 1200, "1200-09-01", "1200-09-30")),
        ("-50", (-50, -50, "-50", "-50")),
        ("1966-1998", (None, None, None, None)),
        (True, (None, None, None, None)),
    ],
)
def test_parse_temporal_bounds_keeps_iso_precision(value, expected) -> None:
    """Verify that ISO bounds keep month and day precision, with sane fallbacks."""
    assert parse_temporal_bounds(value) == expected


def test_enrich_temporal_metadata_keeps_month_precision_in_iso_bounds() -> None:
    """Verify the case reported on the cartulaires: '1200-09' must give September bounds."""
    temporal = enrich_temporal_metadata(
        {
            "dublincore": {"title": "IV (Septembre 1200)", "date": "1200-09"},
            "extensions": {"dateCreated": "1200-09"},
        }
    )

    assert temporal["dublincore.date_start"] == 1200
    assert temporal["dublincore.date_end"] == 1200
    assert temporal["dublincore.date_start_iso"] == "1200-09-01"
    assert temporal["dublincore.date_end_iso"] == "1200-09-30"
    assert temporal["extensions.dateCreated_start_iso"] == "1200-09-01"
    assert temporal["extensions.dateCreated_end_iso"] == "1200-09-30"


# --------------------------------------------------------------------------- #
# Client pipeline and exports
# --------------------------------------------------------------------------- #


def _cartulaire_client(fragment_params: dict | None, **kwargs) -> ThunderDots:
    options = {"use_cache": False, "verbose": False, "concurrency": 2}
    options.update(kwargs)
    return ThunderDots(
        endpoint_dts="https://example.org/api/dts",
        collection_params={"collection_id": "CART_SAMPLE_COLL"},
        resource_params={
            "fragment_mode": "navigation",
            "metadata_dublincore": None,
            "metadata_extensions": None,
            "add_head_to_content": False,
        },
        fragment_params=fragment_params,
        **options,
    )


def test_client_computes_fragment_temporal_only_when_requested(patch_client_fetcher) -> None:
    """Verify the end-to-end behaviour: no temporal key by default, per-fragment index on request."""
    td_default = _cartulaire_client(None)
    td_default.fetch()
    default_fragments = td_default.results()["resource_results"][0]["fragments"]

    assert default_fragments
    assert all("temporal" not in fragment for fragment in default_fragments)
    assert all("metadata" in fragment for fragment in default_fragments)

    td = _cartulaire_client(
        {
            "metadata_dublincore": None,
            "metadata_extensions": None,
            "temporal_xpath": DOCDATE_XPATH,
        },
        validate=True,
    )
    td.fetch()
    resource = td.results()["resource_results"][0]
    fragments = _by_id(resource["fragments"])

    assert resource["metadata"]["dublincore"]["coverage"] == "1157/1185"

    assert fragments["CART_SAMPLE_0001"]["temporal"]["tei.date_start"] == 1157
    assert fragments["CART_SAMPLE_0003"]["temporal"]["tei.date_end"] == 1185
    assert fragments["CART_SAMPLE_notice"]["temporal"] == {}

    # Resource-level dates are never inherited by fragments.
    assert all("dublincore.coverage" not in fragment["temporal"] for fragment in fragments.values())

    assert td.results()["validation"]["output"]["ok"] is True
    report = validate_many(td.results()["resource_results"], profile="resource_result")
    assert report.summary()["invalid"] == 0


def test_client_fragment_temporal_survives_json_cache(tmp_path, patch_client_fetcher) -> None:
    """Verify that the fragment temporal index is persisted and reloaded from the JSON cache."""
    output_path = tmp_path / "results.json"

    td = _cartulaire_client(
        {"metadata_dublincore": ["title"], "temporal_xpath": DOCDATE_XPATH},
        output_path=str(output_path),
        use_cache=True,
    )
    td.fetch()

    td_cached = ThunderDots(
        endpoint_dts="https://example.org/api/dts",
        output_path=str(output_path),
        use_cache=True,
        verbose=False,
    )
    td_cached.fetch()

    fragment = td_cached.notices()[0].fragment_objects()[3]
    assert fragment.id == "CART_SAMPLE_0001"
    assert fragment.temporal_index["tei.date_start"] == 1157
    assert fragment.dublincore == {"title": "Donation de Louis VII."}


def test_fragment_objects_and_qdrant_fragment_points(patch_client_fetcher) -> None:
    """Verify Fragment objects and per-fragment Qdrant exports, with explicit resource provenance."""
    td = _cartulaire_client(
        {"metadata_dublincore": None, "metadata_extensions": None, "temporal_xpath": DOCDATE_XPATH}
    )
    td.fetch()

    notice = td.notices()[0]
    fragments = notice.fragment_objects()
    assert all(isinstance(fragment, Fragment) for fragment in fragments)
    assert len(fragments) == 6

    payloads = td.to_qdrant_fragment_payloads()
    points = td.to_qdrant_fragment_points()

    # Fragments without content (pure containers) are skipped.
    assert [payload["fragment_id"] for payload in payloads] == [
        "CART_SAMPLE_notice",
        "CART_SAMPLE_0001",
        "CART_SAMPLE_0002",
        "CART_SAMPLE_0003",
    ]
    assert len(points) == len(payloads)

    act = payloads[1]
    assert act["record_id"] == "CART_SAMPLE"
    assert act["type"] == "Fragment"
    assert act["title"] == "Cartulaire de test"
    assert act["linked_parents"] == ["CART_SAMPLE_COLL"]
    assert act["temporal"]["tei.date_start"] == 1157
    assert act["temporal__tei__date_start"] == 1157
    assert act["dublincore__title"] == "Donation de Louis VII."
    assert "resource_temporal" not in act

    assert points[1]["id"] == stable_int_id("CART_SAMPLE::CART_SAMPLE_0001")
    assert "vector" not in points[1]

    with_resource = td.to_qdrant_fragment_payloads(include_resource_temporal=True)
    assert with_resource[0]["fragment_id"] == "CART_SAMPLE_notice"
    assert with_resource[0]["temporal"] == {}
    assert with_resource[0]["resource_temporal"]["dublincore.coverage_start"] == 1157
    assert with_resource[0]["resource_temporal__dublincore__coverage_end"] == 1185

    vectors = [[0.0, float(index)] for index in range(len(points))]
    with_vectors = td.to_qdrant_fragment_points(vectors=vectors)
    assert with_vectors[-1]["vector"] == vectors[-1]

    with pytest.raises(ValueError, match="vectors length mismatch"):
        td.to_qdrant_fragment_points(vectors=vectors[:-1])


def test_fragment_temporal_index_property_computes_when_missing() -> None:
    """Verify that Fragment.temporal_index falls back to computing the index from metadata."""
    fragment = Fragment.from_dict(
        {
            "id": "f1",
            "content": "text",
            "metadata": {"dublincore": {"date": "1250-06"}},
        }
    )

    assert fragment.temporal is None
    assert fragment.temporal_index["dublincore.date_start"] == 1250

    stored = Fragment.from_dict({"id": "f2", "content": "text", "temporal": {}})
    assert stored.temporal_index == {}
