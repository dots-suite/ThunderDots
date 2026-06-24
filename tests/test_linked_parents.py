from __future__ import annotations

import asyncio

from thunderdots import ThunderDots
from thunderdots.extract.parents import (
    LinkedParentsResolver,
    extract_linked_parent_ids,
    normalize_parent_ids,
)


def test_normalize_parent_ids_removes_duplicates_and_invalid_values() -> None:
    assert normalize_parent_ids(
        [
            "ENCPOS",
            "",
            " ENCPOS ",
            None,
            "OTHER",
            12,
        ]
    ) == [
        "ENCPOS",
        "OTHER",
    ]


def test_extract_linked_parent_ids_reads_member_ids() -> None:
    payload = {
        "member": [
            {"@id": "ENCPOS"},
            {"@id": "OTHER"},
            {"@id": "ENCPOS"},
        ]
    }

    assert extract_linked_parent_ids(payload) == [
        "ENCPOS",
        "OTHER",
    ]


def test_extract_linked_parent_ids_ignores_malformed_members() -> None:
    payload = {
        "member": [
            None,
            "ENCPOS",
            {},
            {"@id": None},
            {"@id": ""},
            {"id": "ENCPOS_1972"},
        ]
    }

    assert extract_linked_parent_ids(payload) == [
        "ENCPOS_1972",
    ]


def test_extract_linked_parent_ids_handles_missing_member() -> None:
    assert extract_linked_parent_ids({}) == []
    assert extract_linked_parent_ids(None) == []
    assert extract_linked_parent_ids({"member": {}}) == []


def test_client_fetches_collection_and_resource_linked_parents(
    patch_client_fetcher,
) -> None:
    td = ThunderDots(
        endpoint_dts="https://example.org/api/dts",
        collection_params={
            "collection_id": "ENCPOS_2025",
            "fetch_linked_parents": True,
        },
        resource_params={
            "fragment_mode": "document",
            "fetch_linked_parents": True,
        },
        use_cache=False,
        verbose=False,
        concurrency=2,
    )

    td.fetch()
    results = td.results()

    assert results["collection_results"][0]["linked_parents"] == ["ENCPOS"]

    resources_by_id = {resource["id"]: resource for resource in results["resource_results"]}

    assert resources_by_id["ENCPOS_2025_01"]["linked_parents"] == ["ENCPOS_2025"]

    assert resources_by_id["ENCPOS_2025_02"]["linked_parents"] == ["ENCPOS_2025"]

    parent_calls = [
        params
        for path, params in patch_client_fetcher.calls
        if path == "/collection" and params and params.get("nav") == "parents"
    ]

    assert {params["id"] for params in parent_calls} == {
        "ENCPOS_2025",
        "ENCPOS_2025_01",
        "ENCPOS_2025_02",
    }


def test_linked_parents_can_be_disabled(
    patch_client_fetcher,
) -> None:
    td = ThunderDots(
        endpoint_dts="https://example.org/api/dts",
        collection_params={
            "collection_id": "ENCPOS_2025",
            "fetch_linked_parents": False,
        },
        resource_params={
            "fragment_mode": "document",
            "fetch_linked_parents": False,
        },
        use_cache=False,
        verbose=False,
        concurrency=2,
    )

    td.fetch()
    results = td.results()

    # Starting collection has no traversal parent.
    assert results["collection_results"][0]["linked_parents"] == []

    # Resources still receive the direct parent discovered by traversal.
    assert all(
        resource["linked_parents"] == ["ENCPOS_2025"] for resource in results["resource_results"]
    )

    assert not any(
        path == "/collection" and params and params.get("nav") == "parents"
        for path, params in patch_client_fetcher.calls
    )


def test_parent_resolver_uses_cache(
    fixture_fetcher,
) -> None:
    async def run() -> None:
        resolver = LinkedParentsResolver(fixture_fetcher)

        first, second = await asyncio.gather(
            resolver.resolve("ENCPOS_2025_01"),
            resolver.resolve("ENCPOS_2025_01"),
        )

        assert first == ["ENCPOS_2025"]
        assert second == ["ENCPOS_2025"]

    asyncio.run(run())

    parent_calls = [
        call
        for call in fixture_fetcher.calls
        if call[0] == "/collection"
        and call[1]
        and call[1].get("nav") == "parents"
        and call[1].get("id") == "ENCPOS_2025_01"
    ]

    assert len(parent_calls) == 1
