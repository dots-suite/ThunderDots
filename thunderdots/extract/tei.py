# -*- coding: utf-8 -*-

"""tei.py

Extract text fragments from TEI XML, using optional navigation JSON for structure.
"""

from __future__ import annotations
import unicodedata
import hashlib
from copy import deepcopy
from lxml import etree


NS = {"tei": "http://www.tei-c.org/ns/1.0"}
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
PARSER = etree.XMLParser(recover=False, huge_tree=False, remove_comments=True)


def _parse_tei_xml(tei_xml: str | bytes) -> etree._Element:
    """
    Parse un document TEI depuis une chaîne str ou bytes.

    lxml refuse les chaînes Unicode qui contiennent une déclaration XML
    avec encoding, par exemple :
    <?xml version="1.0" encoding="UTF-8"?>

    Pour rendre l'entrée robuste, on encode systématiquement les str en UTF-8.
    """
    if isinstance(tei_xml, str):
        tei_xml = tei_xml.encode("utf-8")

    return etree.fromstring(tei_xml, parser=PARSER)


def _node_xml_id(node: etree._Element) -> str | None:
    return node.get(XML_ID)


def _stable_fragment_id(prefix: str, resource_id: str | None, index: int, text: str) -> str:
    base = f"{resource_id or ''}::{index}::{text}"
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}{digest}"


def _first_text_by_xpath(node: etree._Element, xpath: str | None) -> str | None:
    if not xpath:
        return None

    matches = node.xpath(xpath, namespaces=NS)

    if not matches:
        return None

    first = matches[0]

    if isinstance(first, etree._Element):
        return _normalize_ws("".join(first.itertext()))

    return _normalize_ws(str(first))


def _text_content_without_local_heads(
    node: etree._Element,
    *,
    head_xpath: str = "./tei:head",
) -> str:
    node_copy = deepcopy(node)

    for head in node_copy.xpath(head_xpath, namespaces=NS):
        parent = head.getparent()
        if parent is not None:
            parent.remove(head)

    return _normalize_ws("".join(node_copy.itertext()))


def _nearest_ancestor_head(node: etree._Element) -> str | None:
    cur = node.getparent()
    while cur is not None:
        heads = cur.xpath("./tei:head", namespaces=NS)
        if heads:
            return _normalize_ws(" ".join("".join(h.itertext()) for h in heads))
        cur = cur.getparent()
    return None


def extract_fragments_by_xpath(
    tei_xml: str,
    *,
    fragment_xpath: str,
    resource_id: str | None = None,
    title_xpath: str = "./tei:head",
    remove_fragment_heads: bool = True,
    add_head_to_content: bool = False,
    exclude_heads_contains: list[str] | None = None,
    include_breadcrumb: bool = True,
    generated_id_prefix: str = "__DOCUMENT__",
) -> list[dict]:
    root = _parse_tei_xml(tei_xml)
    nodes = root.xpath(fragment_xpath, namespaces=NS)

    fragments: list[dict] = []

    for index, node in enumerate(nodes):
        if not isinstance(node, etree._Element):
            continue

        head = _first_text_by_xpath(node, title_xpath)
        if head is None:
            head = _nearest_ancestor_head(node)

        if _should_exclude_head(head, exclude_heads_contains):
            continue

        if remove_fragment_heads:
            content = _text_content_without_local_heads(node, head_xpath=title_xpath)
        else:
            content = _normalize_ws("".join(node.itertext()))

        if add_head_to_content and head:
            content = _normalize_ws(f"{head} {content}")
        else:
            content = _strip_leading_head(content, head)

        if not content:
            continue

        xml_id = _node_xml_id(node)
        dots_id = xml_id or _stable_fragment_id(
            generated_id_prefix,
            resource_id,
            index,
            content,
        )

        item = {
            "dots_id": dots_id,
            "head": head,
            "content": content,
            "fragment_xpath": fragment_xpath,
            "fragment_index": index,
        }

        if include_breadcrumb:
            item["breadcrumb"] = head or ""

        fragments.append(item)

    return fragments


def _short_id(value: str | None) -> str | None:
    if not value:
        return None
    value = str(value)
    if "#" in value:
        return value.rsplit("#", 1)[-1]
    if "/" in value:
        return value.rstrip("/").rsplit("/", 1)[-1]
    return value


def _nav_members(nav_json) -> list[dict]:
    if not isinstance(nav_json, dict):
        return []

    members = nav_json.get("member")
    if isinstance(members, list):
        return members

    resource = nav_json.get("resource")
    if isinstance(resource, dict):
        members = resource.get("member")
        if isinstance(members, list):
            return members

    return []


def _nav_title(m: dict) -> str | None:
    dc = m.get("dublincore") or m.get("dublinCore") or {}
    if isinstance(dc, dict):
        title = dc.get("title")
        if title:
            return str(title)

    title = m.get("title")
    return str(title) if title else None


def _nav_identifier(m: dict) -> str | None:
    value = m.get("identifier") or m.get("@id") or m.get("id")
    return _short_id(value)


def _max_cite_depth(nav_json) -> int:
    if not isinstance(nav_json, dict):
        return 0

    candidates = [
        nav_json,
        nav_json.get("resource") if isinstance(nav_json.get("resource"), dict) else {},
    ]

    for candidate in candidates:
        try:
            citation_trees = candidate.get("citationTrees") or {}
            value = citation_trees.get("maxCiteDepth")
            if value is not None:
                return int(value or 0)
        except Exception:
            continue

    members = _nav_members(nav_json)
    return 1 if members else 0


def _normalize_ws(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _strip_leading_head(content: str, head: str | None) -> str:
    """Remove heading prefix from content if it is duplicated at the start."""
    normalized_content = _normalize_ws(content)
    normalized_head = _normalize_ws(head or "")

    if not normalized_head:
        return normalized_content

    if normalized_content == normalized_head:
        return ""

    prefix = normalized_head + " "
    if normalized_content.startswith(prefix):
        return normalized_content[len(prefix) :].strip()

    return normalized_content


def _text_content_without_descendant_fragments(
    node: etree._Element,
    current_xml_id: str,
    fragment_ids: set[str],
) -> str:
    """Extract text from a node excluding descendant nodes that are separate fragments."""
    node_copy = deepcopy(node)

    for el in list(node_copy.iter()):
        if el is node_copy:
            continue

        xid = el.get(XML_ID)
        if xid and xid != current_xml_id and xid in fragment_ids:
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)

    return _normalize_ws("".join(node_copy.itertext()))


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
    parent = m.get("parent")
    if isinstance(parent, str):
        return _short_id(parent)

    refs = m.get("references")
    if isinstance(refs, list) and refs:
        r0 = refs[0]
        if isinstance(r0, dict):
            return _short_id(r0.get("@id") or r0.get("id"))

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


def _normalize_match_text(text: str | None) -> str:
    text = " ".join((text or "").split()).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _should_exclude_head(head: str | None, exclude_heads_contains: list[str] | None) -> bool:
    normalized_head = _normalize_match_text(head)
    if not normalized_head:
        return False

    for pattern in exclude_heads_contains or []:
        normalized_pattern = _normalize_match_text(pattern)
        if normalized_pattern and normalized_pattern in normalized_head:
            return True

    return False


def extract_document_text_fast(
    tei_xml: str,
    *,
    add_head_to_content: bool = True,
    exclude_heads_contains: list[str] | None = None,
    include_breadcrumb: bool = True,
) -> list[dict]:
    root = _parse_tei_xml(tei_xml)
    text_el = root.find(".//tei:text", namespaces=NS)

    if text_el is None:
        text = ""
    elif add_head_to_content:
        text = _text_content(text_el)
    else:
        text = _text_content_without_local_heads(
            text_el,
            head_xpath=".//tei:head",
        )

    item = {
        "dots_id": "__DOCUMENT__",
        "content": _normalize_ws(text),
    }

    if include_breadcrumb:
        item["breadcrumb"] = ""

    return [item]


def extract_fragments(
    nav_json,
    tei_xml: str,
    add_head_to_content: bool = True,
    exclude_heads_contains: list[str] | None = None,
    include_breadcrumb: bool = True,
):
    if (not nav_json) or (_max_cite_depth(nav_json) == 0):
        return extract_document_text_fast(
            tei_xml,
            add_head_to_content=add_head_to_content,
            exclude_heads_contains=exclude_heads_contains,
            include_breadcrumb=include_breadcrumb,
        )

    root = _parse_tei_xml(tei_xml)
    xml_index = _index_xml_ids_iter(root)

    members = _nav_members(nav_json)

    nav_idx: dict[str, dict] = {}
    fragment_ids: set[str] = set()

    for m in members:
        mid = _nav_identifier(m)
        if not mid:
            continue

        fragment_ids.add(mid)
        nav_idx[mid] = {
            "parent": _parent_id(m),
            "title": _nav_title(m),
            "level": m.get("level"),
        }

    fragments = []
    for m in members:
        xml_id = _nav_identifier(m)
        if not xml_id:
            continue

        node = xml_index.get(xml_id)
        if node is None:
            continue

        head = _nav_title(m)
        if _should_exclude_head(head, exclude_heads_contains):
            continue

        content = _text_content_without_descendant_fragments(
            node=node,
            current_xml_id=xml_id,
            fragment_ids=fragment_ids,
        )

        if not add_head_to_content:
            content = _strip_leading_head(content, head)
        else:
            content = _normalize_ws(content)

        item = {
            "dots_id": xml_id,
            "level": m.get("level"),
            "head": head,
            "content": content,
        }
        if include_breadcrumb:
            item["breadcrumb"] = _breadcrumb(nav_idx, xml_id)
        fragments.append(item)
    return fragments
