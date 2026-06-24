from __future__ import annotations

import pytest

from thunderdots import ThunderDots
from thunderdots.fetcher import HttpxFetcher
from thunderdots.stats import Stats

ENDPOINT_DTS = "https://dev.chartes.psl.eu/dots/api/dts/"


@pytest.mark.network
@pytest.mark.parametrize("collection_id", ["ENCPOS_1900"])
def test_online_fetch_root_collections(collection_id: str) -> None:
    """Verify that configured public DTS collection identifiers can be fetched online."""
    td = ThunderDots(
        endpoint_dts=ENDPOINT_DTS,
        collection_params={"collection_id": collection_id, "metadata_dublincore": ["title"]},
        resource_params={"fetch_document": False, "fetch_navigation": False},
        use_cache=False,
        verbose=False,
        concurrency=4,
        request_timeout=20.0,
        retries=2,
    )

    td.fetch()
    results = td.results()

    assert results["collection_results"] or results["resource_results"]
    assert results["meta"]["requests_total"] > 0


@pytest.mark.network
@pytest.mark.parametrize("resource_id", ["ENCPOS_1907_01", "ENCPOS_1974_05"])
def test_online_fetch_known_resource_documents(resource_id: str) -> None:
    """Verify that selected public DTS resource identifiers expose a document response online."""
    stats = Stats()
    stats.start()
    fetcher = HttpxFetcher(
        endpoint=ENDPOINT_DTS,
        timeout=20.0,
        concurrency=2,
        retries=2,
        backoff_ms=300,
        stats=stats,
    )

    import asyncio

    async def run() -> str:
        try:
            return await fetcher.get_text("/document", params={"resource": resource_id})
        finally:
            await fetcher.aclose()

    text = asyncio.run(run())

    assert len(text) > 100
    assert "<" in text


@pytest.mark.network
def test_online_fetch_navigation_mode_for_encpos_1907() -> None:
    """Verify that an online resource can be fetched through the full navigation fragmentation pipeline."""
    td = ThunderDots(
        endpoint_dts=ENDPOINT_DTS,
        collection_params={"collection_id": "ENCPOS_1907"},
        resource_params={
            "fragment_mode": "navigation",
            "metadata_dublincore": ["title", "creator", "date"],
            "metadata_extensions": ["dct:coverage", "dct:extend"],
            "add_head_to_content": False,
            "include_breadcrumb": True,
        },
        use_cache=False,
        verbose=False,
        concurrency=4,
        request_timeout=20.0,
        retries=2,
    )

    td.fetch()

    assert td.results()["resource_results"]
    assert any(resource.get("fragments") for resource in td.results()["resource_results"])


@pytest.mark.network
@pytest.mark.parametrize(
    ("object_id", "expected_parent"),
    [
        ("ENCPOS_1972", "ENCPOS"),
        ("ENCPOS_1972_02", "ENCPOS_1972"),
    ],
)
def test_online_fetch_linked_parents(
    object_id: str,
    expected_parent: str,
) -> None:
    stats = Stats()
    stats.start()
    fetcher = HttpxFetcher(
        endpoint=ENDPOINT_DTS,
        timeout=20.0,
        concurrency=2,
        retries=2,
        backoff_ms=300,
        stats=stats,
    )
    import asyncio

    async def run() -> dict:
        try:
            payload = await fetcher.get_json(
                "/collection",
                params={
                    "id": object_id,
                    "nav": "parents",
                },
            )
            return payload or {}
        finally:
            await fetcher.aclose()

    payload = asyncio.run(run())
    parent_ids = [
        member.get("@id")
        for member in payload.get("member", [])
        if isinstance(member, dict) and member.get("@id")
    ]
    assert expected_parent in parent_ids
