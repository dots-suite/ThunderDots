#-*- coding: utf-8 -*-

"""tei.py

Extract text fragments from TEI XML, using optional navigation JSON for structure.
"""
from __future__ import annotations

from lxml import etree


NS = {"tei": "http://www.tei-c.org/ns/1.0"}
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
PARSER = etree.XMLParser(recover=False, huge_tree=False, remove_comments=True)

def _index_xml_ids_iter(root: etree._Element) -> dict[str, etree._Element]:
    """Build an index of xml:id to element using iter (memory efficient).

    :param root: Root element of the parsed XML tree.
    :type root: lxml.etree._Element
    :return: Dictionary mapping xml:id values to their corresponding elements.
    :rtype: dict[str, lxml.etree._Element]
    """
    idx = {}
    for el in root.iter():
        xid = el.get(XML_ID)
        if xid:
            idx[xid] = el
    return idx

def _parent_id(m: dict) -> str | None:
    """Get the parent ID from a navigation member, checking 'parent' and 'references'.

    :param m: Navigation member dictionary.
    :type m: dict
    :return: Parent ID if found, otherwise None.
    :rtype: str | None
    """
    if isinstance(m.get("parent"), str):
        return m["parent"]
    refs = m.get("references")
    if isinstance(refs, list) and refs:
        r0 = refs[0]
        if isinstance(r0, dict):
            return r0.get("@id")
    return None

def _breadcrumb(idx: dict[str, dict], xml_id: str) -> str:
    """Construct a breadcrumb string for a given xml_id using the navigation index.

    :param idx: Navigation index mapping xml_id to {parent, title, level}.
    :type idx: dict[str, dict]
    :param xml_id: The xml_id for which to build the breadcrumb.
    :type xml_id: str
    :return: Breadcrumb string representing the path from the root to the given xml_id.
    :rtype: str
    """
    parts = []
    seen = set()
    cur = xml_id

    while cur and cur not in seen:
        seen.add(cur)
        node = idx.get(cur)
        if not node:
            break
        title = node.get("title")
        if title:
            parts.append(title)
        cur = node.get("parent")

    return " > ".join(reversed(parts))

def _text_content(el):
    """Extract text content from an element, normalizing whitespace.

    :param el: The XML element from which to extract text.
    :type el: lxml.etree._Element
    :return: Normalized text content of the element.
    :rtype: str
    """
    return " ".join("".join(el.itertext()).split())

def _max_cite_depth(nav_json) -> int:
    """Safely extract maxCiteDepth from navigation JSON, defaulting to 0 on error.

    :param nav_json: Navigation JSON object.
    :type nav_json: dict
    :return: The maxCiteDepth value if present and valid, otherwise 0.
    :rtype: int
    """
    try:
        return int(nav_json["resource"]["citationTrees"]["maxCiteDepth"] or 0)
    except Exception:
        return 0

def extract_document_text_fast(tei_xml: str) -> list[dict]:
    """
    Fast path CPU: no nav, no xml:id index.
    Just parse + grab tei:text + itertext.

    :param tei_xml: TEI XML string to extract text from.
    :type tei_xml: str
    :return: List containing a single fragment with the entire document text.
    :rtype: list[dict]
    """
    root = etree.fromstring(tei_xml, parser=PARSER)
    text_el = root.find(".//tei:text", namespaces=NS)
    text = _text_content(text_el) if text_el is not None else ""
    return [{"dots_id": "__DOCUMENT__", "content": text, "breadcrumb": ""}]


def extract_fragments(nav_json, tei_xml: str):
    """Extract text fragments from TEI XML using navigation JSON for structure.

    If nav_json is missing or has maxCiteDepth=0, falls back to fast path.

    :param nav_json: Navigation JSON object containing structure information.
    :type nav_json: dict
    :param tei_xml: TEI XML string to extract text from.
    :type tei_xml: str
    :return: List of fragments with dots_id, level, head, breadcrumb, and content
    :rtype: list[dict]
    """
    if (not nav_json) or (_max_cite_depth(nav_json) == 0):
        return extract_document_text_fast(tei_xml)

    # ---------- slow path (needs indexing) ----------
    root = etree.fromstring(tei_xml, parser=PARSER)
    xml_index = _index_xml_ids_iter(root)

    members = nav_json.get("member", []) or []

    # index nav: id -> {parent,title,level}
    nav_idx: dict[str, dict] = {}
    for m in members:
        mid = m.get("identifier")
        if not mid:
            continue
        nav_idx[mid] = {
            "parent": _parent_id(m),
            "title": (m.get("dublincore") or {}).get("title"),
            "level": m.get("level"),
        }

    fragments = []
    for m in members:
        xml_id = m.get("identifier")
        if not xml_id:
            continue

        node = xml_index.get(xml_id)
        if node is None:
            continue

        head = (m.get("dublincore") or {}).get("title")
        fragments.append(
            {
                "dots_id": xml_id,
                "level": m.get("level"),
                "head": head,
                "breadcrumb": _breadcrumb(nav_idx, xml_id),
                "content": _text_content(node),
            }
        )

    return fragments
