from __future__ import annotations


import sys
from pathlib import Path
import json
import os
from typing import Any

import pytest


def _find_project_root(start: Path) -> Path:
    """Return the nearest parent directory that contains the ``thunderdots`` package."""
    current = start.resolve()
    candidates = [current, *current.parents]
    for candidate in candidates:
        if (candidate / "thunderdots" / "__init__.py").exists():
            return candidate
    return start.resolve().parents[1]


PROJECT_ROOT = _find_project_root(Path(__file__).parent)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


FIXTURES_DIR = Path(__file__).parent / "fixtures"
JSON_FIXTURES = FIXTURES_DIR / "json"
XML_FIXTURES = FIXTURES_DIR / "xml"


def load_json(name: str) -> dict[str, Any]:
    return json.loads((JSON_FIXTURES / name).read_text(encoding="utf-8"))


def load_xml(name: str) -> str:
    return (XML_FIXTURES / name).read_text(encoding="utf-8")


class FixtureFetcher:
    """Minimal asynchronous fetcher used to test ThunderDots without network calls."""

    def __init__(self) -> None:
        self.collection = load_json("collection_encpos_2025.json")
        self.resources = {
            "ENCPOS_2025_01": load_json("resource_encpos_2025_01.json"),
            "ENCPOS_2025_02": self.collection["member"][1],
        }
        self.navigation = {
            "ENCPOS_2025_01": load_json("navigation_encpos_2025_01.json"),
            "ENCPOS_2025_02": load_json("navigation_encpos_2025_01.json"),
        }
        self.documents = {
            "ENCPOS_2025_01": load_xml("encpos_1893_05.xml"),
            "ENCPOS_2025_02": load_xml("encpos_1893_05.xml"),
            "SMCP-PR_0004": load_xml("smcp_pr_0004.xml"),
        }
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    async def get_json(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        self.calls.append((path, params))
        params = params or {}
        if path == "/collection":
            resource_id = params.get("id") or "ENCPOS_2025"
            if resource_id == "ENCPOS_2025":
                return self.collection
            return self.resources.get(str(resource_id))
        if path == "/navigation":
            return self.navigation.get(str(params.get("resource")))
        raise AssertionError(f"Unexpected JSON path: {path}")

    async def get_text(self, path: str, params: dict[str, Any] | None = None) -> str:
        self.calls.append((path, params))
        params = params or {}
        if path == "/document":
            resource_id = str(params.get("resource"))
            return self.documents[resource_id]
        raise AssertionError(f"Unexpected text path: {path}")

    async def aclose(self) -> None:
        return None


@pytest.fixture
def fixture_fetcher() -> FixtureFetcher:
    return FixtureFetcher()


@pytest.fixture
def patch_client_fetcher(
    monkeypatch: pytest.MonkeyPatch, fixture_fetcher: FixtureFetcher
) -> FixtureFetcher:
    from thunderdots.client import ThunderDots

    monkeypatch.setattr(ThunderDots, "_make_fetcher", lambda self: fixture_fetcher)
    return fixture_fetcher


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.getenv("RUN_NETWORK_TESTS") == "1":
        return
    skip_network = pytest.mark.skip(reason="set RUN_NETWORK_TESTS=1 to run online DTS tests")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip_network)
