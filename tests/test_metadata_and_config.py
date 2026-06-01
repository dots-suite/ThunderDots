from __future__ import annotations

import pytest

from conftest import load_json
from thunderdots.config import CollectionParams, ResourceParams
from thunderdots.normalize.dates import enrich_temporal_metadata
from thunderdots.normalize.metadata import build_metadata, canonicalize_metadata_keys


def test_build_metadata_keeps_requested_dublincore_and_extensions() -> None:
    """Verify that metadata selection keeps explicit Dublin Core and extension fields only."""
    resource = load_json("resource_encpos_2025_01.json")

    metadata = build_metadata(
        resource,
        metadata_dublincore=["creator", "date", "title"],
        metadata_extensions=["dct:coverage", "dct:extend", "download"],
    )

    assert metadata["dublincore"]["creator"] == "Marie Auzel"
    assert metadata["dublincore"]["date"] == 2025
    assert metadata["extensions"]["dct:coverage"] == "1280/1284"
    assert "dct:rights" not in metadata["extensions"]


def test_build_metadata_none_keeps_all_metadata() -> None:
    """Verify that None means keep all metadata while an empty list means keep none."""
    resource = load_json("resource_encpos_2025_01.json")

    metadata = build_metadata(
        resource,
        metadata_dublincore=None,
        metadata_extensions=[],
    )

    assert metadata["dublincore"]["creator"] == "Marie Auzel"
    assert "extensions" not in metadata


def test_canonicalize_metadata_accepts_dublin_core_spelling() -> None:
    """Verify that dublinCore is normalized to dublincore for consistent downstream access."""
    normalized = canonicalize_metadata_keys({"dublinCore": {"title": "Title"}})

    assert normalized == {"dublincore": {"title": "Title"}}


def test_legacy_keep_metadata_is_split_between_dc_and_extensions() -> None:
    """Verify that deprecated keep_metadata paths are converted into explicit metadata parameters."""
    with pytest.warns(DeprecationWarning):
        params = ResourceParams.from_dict(
            {"keep_metadata": ["dublincore.creator", "dct:coverage", "extensions.download"]}
        )

    assert params.metadata_dublincore == ["creator"]
    assert params.metadata_extensions == ["dct:coverage", "download"]


def test_collection_params_default_to_none_metadata_filters() -> None:
    """Verify collection metadata defaults keep all metadata when no filter is configured."""
    params = CollectionParams.from_dict({"collection_id": "ENCPOS_2025"})

    assert params.collection_id == "ENCPOS_2025"
    assert params.metadata_dublincore is None
    assert params.metadata_extensions is None


def test_enrich_temporal_metadata_builds_year_bounds() -> None:
    """Verify that temporal metadata fields produce numeric and ISO year bounds."""
    enriched = enrich_temporal_metadata({"coverage": "1280/1284", "date": 2025})

    assert enriched["coverage_start"] == 1280
    assert enriched["coverage_end"] == 1284
    assert enriched["date_start_iso"] == "2025-01-01"
    assert enriched["date_end_iso"] == "2025-12-31"
