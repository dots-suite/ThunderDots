from __future__ import annotations

import csv
import json
from pathlib import Path

from thunderdots import ThunderDots


def test_client_offline_fetches_collection_resources_and_navigation_fragments(
    patch_client_fetcher,
) -> None:
    """Verify that ThunderDots can fetch a complete DTS-like corpus through a mocked fetcher."""
    td = ThunderDots(
        endpoint_dts="https://example.org/api/dts",
        collection_params={"collection_id": "ENCPOS_2025", "metadata_dublincore": ["title"]},
        resource_params={
            "fragment_mode": "navigation",
            "metadata_dublincore": ["creator", "date", "title"],
            "metadata_extensions": ["dct:coverage", "dct:extend"],
            "add_head_to_content": False,
            "include_breadcrumb": True,
            "exclude_heads_contains": ["pièces justificatives"],
        },
        use_cache=False,
        verbose=False,
        concurrency=2,
    )

    td.fetch()
    results = td.results()

    assert results["type"] == "All"
    assert len(results["collection_results"]) == 1
    assert len(results["resource_results"]) == 2
    assert results["resource_results"][0]["metadata"]["dublincore"]
    assert all(resource["fragments"] for resource in results["resource_results"])
    assert any(call[0] == "/navigation" for call in patch_client_fetcher.calls)


def test_client_offline_document_mode_does_not_call_navigation(patch_client_fetcher) -> None:
    """Verify that document mode fetches documents without requesting DTS navigation."""
    td = ThunderDots(
        endpoint_dts="https://example.org/api/dts",
        collection_params={"collection_id": "ENCPOS_2025"},
        resource_params={"fragment_mode": "document", "fetch_navigation": False},
        use_cache=False,
        verbose=False,
        concurrency=2,
    )

    td.fetch()

    assert td.results()["resource_results"]
    assert not any(call[0] == "/navigation" for call in patch_client_fetcher.calls)


def test_client_offline_xpath_mode_uses_configured_xpath(patch_client_fetcher) -> None:
    """Verify that TEI XPath mode applies user-defined XPath extraction through the client."""
    td = ThunderDots(
        endpoint_dts="https://example.org/api/dts",
        collection_params={"collection_id": "ENCPOS_2025"},
        resource_params={
            "fragment_mode": "tei_xpath",
            "fragment_xpath": ".//tei:text/tei:body/tei:div",
            "title_xpath": "./tei:head",
            "remove_fragment_heads": True,
            "add_head_to_content": False,
            "exclude_heads_contains": ["bibliographie", "pièces justificatives"],
        },
        use_cache=False,
        verbose=False,
        concurrency=2,
    )

    td.fetch()
    first = td.results()["resource_results"][0]

    assert {fragment["id"] for fragment in first["fragments"]} == {"intro", "chap1"}
    assert all("fragment_xpath" in fragment for fragment in first["fragments"])


def test_client_writes_and_reloads_json_cache(tmp_path: Path, patch_client_fetcher) -> None:
    """Verify that output_path is written and later reused when use_cache is enabled."""
    output_path = tmp_path / "results.json"

    td = ThunderDots(
        endpoint_dts="https://example.org/api/dts",
        collection_params={"collection_id": "ENCPOS_2025"},
        resource_params={"fragment_mode": "document"},
        output_path=str(output_path),
        use_cache=True,
        verbose=False,
    )
    td.fetch()

    assert output_path.exists()
    cached = json.loads(output_path.read_text(encoding="utf-8"))
    assert cached["resource_results"]

    patch_client_fetcher.calls.clear()
    td_cached = ThunderDots(
        endpoint_dts="https://example.org/api/dts",
        output_path=str(output_path),
        use_cache=True,
        verbose=False,
    )
    td_cached.fetch()

    assert td_cached.results()["resource_results"] == cached["resource_results"]
    assert patch_client_fetcher.calls == []


def test_client_writes_flat_csv_cache(tmp_path: Path, patch_client_fetcher) -> None:
    """Verify that cache_csv_path writes a flat CSV index of fetched resources."""
    csv_path = tmp_path / "resources.csv"

    td = ThunderDots(
        endpoint_dts="https://example.org/api/dts",
        collection_params={"collection_id": "ENCPOS_2025"},
        resource_params={
            "fragment_mode": "document",
            "metadata_dublincore": ["creator", "date"],
            "metadata_extensions": ["dct:coverage"],
        },
        cache_csv_path=str(csv_path),
        use_cache=False,
        verbose=False,
    )
    td.fetch()

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    assert len(rows) == 2
    assert "dublincore.creator" in rows[0]
    assert "extensions.dct:coverage" in rows[0]
