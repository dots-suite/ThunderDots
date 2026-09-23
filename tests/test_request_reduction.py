from __future__ import annotations

import asyncio
import subprocess
import sys

import httpx
import pytest

from thunderdots import ThunderDots
from thunderdots.config import CollectionParams, ResourceParams
from thunderdots.extract.walker import member_describes_resource, member_gives_single_parent
from thunderdots.fetcher import HttpxFetcher, build_limits
from thunderdots.stats import Stats
from thunderdots.validation.validators import _validator_for


def _calls(fetcher, path: str, **params):
    """Return the recorded calls matching *path* and the given query parameters."""
    return [
        call_params
        for call_path, call_params in fetcher.calls
        if call_path == path and all((call_params or {}).get(k) == v for k, v in params.items())
    ]


def _resource_fetches(fetcher):
    return [
        params
        for params in _calls(fetcher, "/collection")
        if params and params.get("id", "").startswith("ENCPOS_2025_") and "nav" not in params
    ]


def _parents_calls(fetcher):
    return _calls(fetcher, "/collection", nav="parents")


def _client(patch_client_fetcher, collection_params=None, resource_params=None) -> ThunderDots:
    return ThunderDots(
        endpoint_dts="https://example.org/api/dts",
        collection_params={"collection_id": "ENCPOS_2025", **(collection_params or {})},
        resource_params={"fragment_mode": "document", **(resource_params or {})},
        use_cache=False,
        verbose=False,
        concurrency=2,
    )


# --------------------------------------------------------------------------- #
# Member hints (lot A)
# --------------------------------------------------------------------------- #


def test_default_walk_skips_resource_fetches_and_parent_requests(patch_client_fetcher) -> None:
    """Verify that complete member entries and totalParents avoid two requests per resource."""
    td = _client(
        patch_client_fetcher,
        resource_params={
            "metadata_dublincore": ["creator", "date"],
            "metadata_extensions": ["dct:coverage"],
        },
    )
    td.fetch()
    results = td.results()

    # Only the root collection is described through /collection and nav=parents.
    assert _resource_fetches(patch_client_fetcher) == []
    assert [params["id"] for params in _parents_calls(patch_client_fetcher)] == ["ENCPOS_2025"]

    # Documents are still fetched, results are complete.
    assert len(_calls(patch_client_fetcher, "/document")) == 2
    by_id = {resource["id"]: resource for resource in results["resource_results"]}
    assert by_id["ENCPOS_2025_01"]["metadata"]["dublincore"]["creator"] == "Marie Auzel"
    assert by_id["ENCPOS_2025_01"]["metadata"]["extensions"]["dct:coverage"] == "1280/1284"
    assert by_id["ENCPOS_2025_01"]["linked_parents"] == ["ENCPOS_2025"]
    assert by_id["ENCPOS_2025_02"]["linked_parents"] == ["ENCPOS_2025"]
    assert results["collection_results"][0]["linked_parents"] == ["ENCPOS"]

    # 2 resource descriptions + 2 parents requests avoided.
    assert td.stats()["requests_skipped"] == 4
    assert results["meta"]["requests_skipped"] == 4


def test_auto_mode_refetches_when_a_requested_key_is_missing_from_member(
    patch_client_fetcher,
) -> None:
    """Verify that a member entry lacking an explicitly requested key is not trusted."""
    # dct:publisher only exists in the full resource description, not in the member entry.
    td = _client(patch_client_fetcher, resource_params={"metadata_extensions": ["dct:publisher"]})
    td.fetch()

    fetched = {params["id"] for params in _resource_fetches(patch_client_fetcher)}
    assert fetched == {"ENCPOS_2025_01", "ENCPOS_2025_02"}

    by_id = {resource["id"]: resource for resource in td.results()["resource_results"]}
    assert by_id["ENCPOS_2025_01"]["metadata"]["extensions"]["dct:publisher"] == (
        "Ecole nationale des chartes"
    )
    # Parents are still taken from totalParents.
    assert [params["id"] for params in _parents_calls(patch_client_fetcher)] == ["ENCPOS_2025"]
    assert td.stats()["requests_skipped"] == 2


def test_auto_mode_refetches_members_without_structural_keys(patch_client_fetcher) -> None:
    """Verify that a member entry without citationTrees/document is fetched in auto mode."""
    member = patch_client_fetcher.collection["member"][0]
    member.pop("citationTrees")
    member.pop("document")

    td = _client(patch_client_fetcher)
    td.fetch()

    fetched = {params["id"] for params in _resource_fetches(patch_client_fetcher)}
    assert fetched == {"ENCPOS_2025_01"}


def test_trust_flags_can_be_disabled(patch_client_fetcher) -> None:
    """Verify that disabling both flags restores one /collection and one nav=parents per object."""
    td = _client(
        patch_client_fetcher,
        collection_params={"trust_member_metadata": False, "trust_total_parents": False},
    )
    td.fetch()

    assert {params["id"] for params in _resource_fetches(patch_client_fetcher)} == {
        "ENCPOS_2025_01",
        "ENCPOS_2025_02",
    }
    assert {params["id"] for params in _parents_calls(patch_client_fetcher)} == {
        "ENCPOS_2025",
        "ENCPOS_2025_01",
        "ENCPOS_2025_02",
    }
    assert td.stats()["requests_skipped"] == 0


def test_trust_member_metadata_true_forces_member_use(patch_client_fetcher) -> None:
    """Verify that trust_member_metadata=True uses member entries even when keys are missing."""
    td = _client(
        patch_client_fetcher,
        collection_params={"trust_member_metadata": True},
        resource_params={"metadata_extensions": ["dct:publisher"]},
    )
    td.fetch()

    assert _resource_fetches(patch_client_fetcher) == []
    by_id = {resource["id"]: resource for resource in td.results()["resource_results"]}
    assert "extensions" not in by_id["ENCPOS_2025_01"]["metadata"]


def test_parents_request_kept_when_total_parents_is_not_one(patch_client_fetcher) -> None:
    """Verify that totalParents != 1 (or missing) keeps the nav=parents request."""
    members = patch_client_fetcher.collection["member"]
    members[0]["totalParents"] = 2
    del members[1]["totalParents"]

    td = _client(patch_client_fetcher)
    td.fetch()

    assert {params["id"] for params in _parents_calls(patch_client_fetcher)} == {
        "ENCPOS_2025",
        "ENCPOS_2025_01",
        "ENCPOS_2025_02",
    }


def test_linked_parents_disabled_never_requests_parents(patch_client_fetcher) -> None:
    """Verify that fetch_linked_parents=False keeps traversal parents without any request."""
    td = _client(
        patch_client_fetcher,
        collection_params={"fetch_linked_parents": False},
        resource_params={"fetch_linked_parents": False},
    )
    td.fetch()

    assert _parents_calls(patch_client_fetcher) == []
    assert all(
        resource["linked_parents"] == ["ENCPOS_2025"]
        for resource in td.results()["resource_results"]
    )


@pytest.mark.parametrize(
    ("member", "mode", "resource_params", "expected"),
    [
        (None, "auto", {}, False),
        ({"@type": "Collection", "citationTrees": {}, "dublincore": {}}, "auto", {}, False),
        ({"@type": "Resource", "dublincore": {"title": "t"}}, "auto", {}, False),
        ({"@type": "Resource", "citationTrees": {}}, "auto", {}, False),
        (
            {"@type": "Resource", "citationTrees": {}, "dublinCore": {"title": "t"}},
            "auto",
            {},
            True,
        ),
        (
            {"@type": "Resource", "document": "/doc", "dublincore": {"title": "t"}},
            "auto",
            {"metadata_dublincore": ["title", "creator"]},
            False,
        ),
        (
            {"@type": "Resource", "document": "/doc", "dublincore": {"title": "t"}},
            "auto",
            {"metadata_dublincore": ["title"], "metadata_extensions": []},
            True,
        ),
        ({"@type": "Resource"}, True, {"metadata_dublincore": ["title"]}, True),
        (
            {"@type": "Resource", "citationTrees": {}, "dublincore": {"title": "t"}},
            False,
            {},
            False,
        ),
    ],
)
def test_member_describes_resource(member, mode, resource_params, expected) -> None:
    """Verify the completeness rules applied to member entries."""
    params = ResourceParams.from_dict(resource_params)
    assert member_describes_resource(member, mode=mode, resource_params=params) is expected


@pytest.mark.parametrize(
    ("member", "traversal", "expected"),
    [
        ({"totalParents": 1}, ["A"], True),
        ({"totalParents": 1}, [], False),
        ({"totalParents": 2}, ["A"], False),
        ({"totalParents": 0}, ["A"], False),
        ({"totalParents": "1"}, ["A"], False),
        ({"totalParents": True}, ["A"], False),
        ({}, ["A"], False),
        (None, ["A"], False),
    ],
)
def test_member_gives_single_parent(member, traversal, expected) -> None:
    """Verify when totalParents allows skipping the parents request."""
    assert member_gives_single_parent(member, traversal) is expected


@pytest.mark.parametrize("value", ["yes", 1, None])
def test_collection_params_reject_invalid_trust_member_metadata(value) -> None:
    with pytest.raises(ValueError):
        CollectionParams.from_dict({"trust_member_metadata": value})


def test_collection_params_trust_defaults() -> None:
    params = CollectionParams.from_dict({"collection_id": "X", "trust_member_metadata": "AUTO"})
    assert params.trust_member_metadata == "auto"
    assert params.trust_total_parents is True
    assert CollectionParams.from_dict(None).trust_member_metadata == "auto"


# --------------------------------------------------------------------------- #
# Network and imports (lot B)
# --------------------------------------------------------------------------- #


def test_pool_limits_keep_every_connection_alive() -> None:
    """Verify that the pool no longer closes half of its connections between bursts."""
    limits = build_limits(20)
    assert limits.max_connections == 20
    assert limits.max_keepalive_connections == 20

    assert build_limits(0).max_connections == 20
    assert build_limits(1000).max_connections == 200


def test_import_does_not_load_jsonschema_or_rich() -> None:
    """Verify that heavy imports are deferred until validation or the progress UI is used.

    httpx's optional CLI module may import ``rich`` on its own when the package is
    installed, which is outside ThunderDots' control: only the modules added on top of
    ``import httpx`` are checked.
    """
    code = (
        "import sys, httpx\n"
        "before = set(sys.modules)\n"
        "import thunderdots\n"
        "added = sorted(m for m in sys.modules if m not in before "
        "and (m.startswith('rich') or m.startswith('jsonschema')))\n"
        "print(added)"
    )
    output = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout
    assert output.strip() == "[]"


def test_stats_expose_requests_skipped() -> None:
    stats = Stats()
    stats.start()
    stats.requests_skipped += 3
    stats.stop()
    assert stats.to_dict()["requests_skipped"] == 3


# --------------------------------------------------------------------------- #
# CPU micro-gains (lot C)
# --------------------------------------------------------------------------- #


def test_httpx_fetcher_get_bytes_returns_raw_body() -> None:
    """Verify that get_bytes hands the raw body back, without decoding."""
    body = '<?xml version="1.0" encoding="UTF-8"?><TEI>é</TEI>'.encode("utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["resource"] == "X"
        return httpx.Response(200, content=body, headers={"content-type": "application/xml"})

    stats = Stats()
    stats.start()
    fetcher = HttpxFetcher(
        endpoint="https://example.org/dts", timeout=5.0, concurrency=2, stats=stats
    )
    fetcher._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def run() -> tuple[bytes, str]:
        try:
            return (
                await fetcher.get_bytes("/document", params={"resource": "X"}),
                await fetcher.get_text("/document", params={"resource": "X"}),
            )
        finally:
            await fetcher.aclose()

    raw, text = asyncio.run(run())
    assert raw == body
    assert "é" in text
    assert stats.requests_total == 2


def test_document_pipeline_accepts_bytes(patch_client_fetcher, monkeypatch) -> None:
    """Verify that the resource pipeline works when the fetcher serves documents as bytes."""
    documents = patch_client_fetcher.documents
    served_as_bytes: list[str] = []

    async def get_bytes(path, params=None):
        resource_id = str((params or {}).get("resource"))
        served_as_bytes.append(resource_id)
        return documents[resource_id].encode("utf-8")

    monkeypatch.setattr(patch_client_fetcher, "get_bytes", get_bytes, raising=False)

    td = _client(patch_client_fetcher)
    td.fetch()

    fragments = td.results()["resource_results"][0]["fragments"]
    assert fragments[0]["id"] == "__DOCUMENT__"
    assert "Jean d’Alençon" in fragments[0]["content"]
    assert sorted(served_as_bytes) == ["ENCPOS_2025_01", "ENCPOS_2025_02"]
    assert not any(path == "/document" for path, _ in patch_client_fetcher.calls)


def test_validators_are_built_once_per_profile() -> None:
    assert _validator_for("resource_result") is _validator_for("resource_result")
    assert _validator_for("output") is not _validator_for("resource_result")
