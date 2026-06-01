from __future__ import annotations

from thunderdots import ThunderDots
from thunderdots.orm import DotsNotice, sanitize_payload_key, stable_int_id
from thunderdots.validation import validate_many, validate_notice


def test_output_validation_accepts_client_results(patch_client_fetcher) -> None:
    """Verify that fetched ThunderDots outputs and resource results pass JSON Schema validation."""
    td = ThunderDots(
        endpoint_dts="https://example.org/api/dts",
        collection_params={"collection_id": "ENCPOS_2025"},
        resource_params={"fragment_mode": "document"},
        validate=True,
        use_cache=False,
        verbose=False,
    )

    td.fetch()
    results = td.results()

    assert results["validation"]["output"]["ok"] is True
    assert results["validation"]["resources"]["invalid"] == 0
    assert validate_notice(results, profile="output").ok is True
    assert (
        validate_many(results["resource_results"], profile="resource_result").summary()["valid"]
        == 2
    )


def test_notice_short_metadata_and_temporal_access(patch_client_fetcher) -> None:
    """Verify that DotsNotice exposes convenient metadata and temporal accessors."""
    td = ThunderDots(
        endpoint_dts="https://example.org/api/dts",
        collection_params={"collection_id": "ENCPOS_2025"},
        resource_params={
            "fragment_mode": "document",
            "metadata_dublincore": ["creator", "date", "title"],
            "metadata_extensions": ["dct:coverage"],
        },
        use_cache=False,
        verbose=False,
    )
    td.fetch()

    notice = td.notices()[0]

    assert isinstance(notice, DotsNotice)
    assert notice.creator_names
    assert notice.date == 2025
    assert notice.date_start == 2025
    assert "dublincore.date_start" in notice.temporal_index


def test_elasticsearch_exports_include_expected_fields(patch_client_fetcher) -> None:
    """Verify that Elasticsearch document and action exports contain text, metadata, and index data."""
    td = ThunderDots(
        endpoint_dts="https://example.org/api/dts",
        collection_params={"collection_id": "ENCPOS_2025"},
        resource_params={"fragment_mode": "document", "metadata_dublincore": ["creator", "date"]},
        use_cache=False,
        verbose=False,
    )
    td.fetch()

    docs = td.to_elastic_documents(include_fragments=True, include_raw=False)
    actions = td.to_elastic_actions(index="thunderdots-test", include_fragments=False)

    assert docs[0]["id"].startswith("ENCPOS_2025_")
    assert docs[0]["text"]
    assert "fragments" in docs[0]
    assert actions[0]["_index"] == "thunderdots-test"
    assert "fragments" not in actions[0]["_source"]


def test_qdrant_exports_include_stable_ids_and_sanitized_metadata(patch_client_fetcher) -> None:
    """Verify that Qdrant payloads and points expose stable IDs and sanitized metadata keys."""
    td = ThunderDots(
        endpoint_dts="https://example.org/api/dts",
        collection_params={"collection_id": "ENCPOS_2025"},
        resource_params={
            "fragment_mode": "document",
            "metadata_dublincore": ["creator", "date"],
            "metadata_extensions": ["dct:coverage"],
        },
        use_cache=False,
        verbose=False,
    )
    td.fetch()

    payloads = td.to_qdrant_payloads(include_fragments=False)
    points = td.to_qdrant_points(vectors=[[0.0, 0.1] for _ in payloads], include_fragments=False)

    assert payloads[0]["record_id"] == payloads[0]["id"]
    assert "dublincore__creator" in payloads[0]
    assert "extensions__dct__coverage" in payloads[0]
    assert points[0]["id"] == stable_int_id(payloads[0]["id"])
    assert points[0]["vector"] == [0.0, 0.1]
    assert sanitize_payload_key("extensions.dct:coverage") == "extensions__dct__coverage"


def test_qdrant_points_reject_vector_count_mismatch(patch_client_fetcher) -> None:
    """Verify that Qdrant point export fails loudly when vector count does not match notices."""
    td = ThunderDots(
        endpoint_dts="https://example.org/api/dts",
        collection_params={"collection_id": "ENCPOS_2025"},
        resource_params={"fragment_mode": "document"},
        use_cache=False,
        verbose=False,
    )
    td.fetch()

    try:
        td.to_qdrant_points(vectors=[[0.0]])
    except ValueError as exc:
        assert "vectors length mismatch" in str(exc)
    else:
        raise AssertionError("Expected ValueError for vector count mismatch")
