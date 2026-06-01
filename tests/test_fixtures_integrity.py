from __future__ import annotations

from lxml import etree

from conftest import load_json, load_xml


def test_collection_fixture_contains_declared_resources() -> None:
    """Verify that the collection fixture exposes resource members with DTS metadata."""
    collection = load_json("collection_encpos_2025.json")

    assert collection["@id"] == "ENCPOS_2025"
    assert collection["@type"] == "Collection"
    assert len(collection["member"]) == 2
    assert collection["member"][0]["citationTrees"]["maxCiteDepth"] == 2
    assert collection["member"][0]["dublincore"]["creator"] == "Marie Auzel"


def test_resource_fixture_contains_dublincore_and_extensions() -> None:
    """Verify that the resource fixture keeps both Dublin Core and extension metadata."""
    resource = load_json("resource_encpos_2025_01.json")

    assert resource["@id"] == "ENCPOS_2025_01"
    assert resource["dublincore"]["date"] == 2025
    assert resource["extensions"]["dct:coverage"] == "1280/1284"
    assert resource["extensions"]["download"].endswith("resource=ENCPOS_2025_01")


def test_xml_fixtures_are_parseable_tei_documents() -> None:
    """Verify that all XML fixtures are well-formed TEI documents usable by the extractors."""
    for filename in ["encpos_1893_05.xml", "smcp_pr_0004.xml"]:
        root = etree.fromstring(load_xml(filename).encode("utf-8"))
        assert root.tag.endswith("TEI")
