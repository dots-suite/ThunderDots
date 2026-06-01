from __future__ import annotations

from conftest import load_json, load_xml
from thunderdots.extract.tei import (
    extract_document_text_fast,
    extract_fragments,
    extract_fragments_by_xpath,
)


def test_document_mode_extracts_single_global_fragment_without_heads() -> None:
    """Verify that document mode returns one global fragment and can remove TEI heads."""
    xml = load_xml("encpos_1893_05.xml")

    fragments = extract_document_text_fast(xml, add_head_to_content=False, include_breadcrumb=True)

    assert len(fragments) == 1
    assert fragments[0]["dots_id"] == "__DOCUMENT__"
    assert "L’origine de Jean d’Alençon" in fragments[0]["content"]
    assert "Chapitre I" not in fragments[0]["content"]
    assert fragments[0]["breadcrumb"] == ""


def test_navigation_mode_uses_nav_ids_and_filters_unwanted_heads() -> None:
    """Verify that navigation mode aligns fragments on navigation IDs and excludes matching heads."""
    xml = load_xml("encpos_1893_05.xml")
    nav = load_json("navigation_encpos_2025_01.json")

    fragments = extract_fragments(
        nav,
        xml,
        add_head_to_content=False,
        exclude_heads_contains=["pièces justificatives"],
        include_breadcrumb=True,
    )

    assert [fragment["dots_id"] for fragment in fragments] == ["intro", "chap1"]
    assert fragments[0]["head"] == "Introduction"
    assert "Texte introductif utile" in fragments[0]["content"]
    assert all("Annexe à exclure" not in fragment["content"] for fragment in fragments)


def test_xpath_mode_extracts_divisions_with_xml_ids() -> None:
    """Verify that TEI XPath mode creates one fragment per selected division with stable XML IDs."""
    xml = load_xml("encpos_1893_05.xml")

    fragments = extract_fragments_by_xpath(
        xml,
        fragment_xpath=".//tei:text/tei:body/tei:div",
        title_xpath="./tei:head",
        remove_fragment_heads=True,
        add_head_to_content=False,
        exclude_heads_contains=["bibliographie", "pièces justificatives"],
        include_breadcrumb=True,
    )

    assert [fragment["dots_id"] for fragment in fragments] == ["intro", "chap1"]
    assert fragments[1]["head"] == "Chapitre I (1405-1415)"
    assert "Chapitre I" not in fragments[1]["content"]
    assert fragments[1]["breadcrumb"] == "Chapitre I (1405-1415)"


def test_xpath_mode_generates_stable_ids_when_xml_id_is_missing() -> None:
    """Verify that TEI XPath mode generates deterministic IDs when selected nodes have no xml:id."""
    xml = load_xml("encpos_1893_05.xml")

    fragments_a = extract_fragments_by_xpath(
        xml,
        fragment_xpath=".//tei:text/tei:body/tei:div/tei:p",
        resource_id="ENCPOS_1893_05",
        generated_id_prefix="__TEST__",
    )
    fragments_b = extract_fragments_by_xpath(
        xml,
        fragment_xpath=".//tei:text/tei:body/tei:div/tei:p",
        resource_id="ENCPOS_1893_05",
        generated_id_prefix="__TEST__",
    )

    assert fragments_a
    assert fragments_a[0]["dots_id"].startswith("__TEST__")
    assert [f["dots_id"] for f in fragments_a] == [f["dots_id"] for f in fragments_b]


def test_xpath_mode_handles_dts_wrapper_documents() -> None:
    """Verify that XPath extraction works on TEI documents containing a DTS wrapper."""
    xml = load_xml("smcp_pr_0004.xml")

    fragments = extract_fragments_by_xpath(
        xml,
        fragment_xpath=".//tei:body/tei:div",
        title_xpath="./tei:head",
        remove_fragment_heads=True,
        add_head_to_content=False,
        include_breadcrumb=True,
    )

    assert len(fragments) == 1
    assert fragments[0]["dots_id"] == "transcription"
    assert "Rotbertus" in fragments[0]["content"]
