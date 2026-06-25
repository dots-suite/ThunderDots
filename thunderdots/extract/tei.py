# -*- coding: utf-8 -*-

"""tei.py

Extract text fragments from TEI XML, using optional navigation JSON for structure.
"""

from __future__ import annotations

import unicodedata
import hashlib
from lxml import etree
import warnings


NS = {"tei": "http://www.tei-c.org/ns/1.0"}
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
PARSER = etree.XMLParser(recover=False, huge_tree=False, remove_comments=True)


def _parse_tei_xml(tei_xml: str | bytes) -> etree._Element:
    """Parse TEI XML string into an lxml Element, using a secure parser configuration.

    :param tei_xml: TEI XML content as a string or bytes
    :type tei_xml: str | bytes
    :return: Root element of the parsed XML tree
    :rtype: lxml.etree._Element
    """
    if isinstance(tei_xml, str):
        tei_xml = tei_xml.encode("utf-8")

    return etree.fromstring(tei_xml, parser=PARSER)


def _node_xml_id(node: etree._Element) -> str | None:
    """Get the xml:id attribute of a node, if it exists.

    :param node: XML element to check for xml:id
    :type node: lxml.etree._Element
    :return: The value of the xml:id attribute, or None if not present
    :rtype: str | None
    """
    return node.get(XML_ID)


def _stable_fragment_id(prefix: str, resource_id: str | None, index: int, text: str) -> str:
    """Generate a stable fragment ID based on the resource ID, fragment index, and content text.

    :param prefix: Prefix to use for the generated ID (e.g. "__DOCUMENT__")
    :type prefix: str
    :param resource_id: Optional resource ID to include in the hash input
    :type resource_id: str | None
    :param index: Fragment index to include in the hash input
    :type index: int
    :param text: Fragment content text to include in the hash input
    :type text: str
    :return: A stable fragment ID string
    :rtype: str
    """
    base = f"{resource_id or ''}::{index}::{text}"
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}{digest}"


def _first_text_by_xpath(node: etree._Element, xpath: str | None) -> str | None:
    """Extract the first text content from a node using an XPath expression, normalizing whitespace.

    :param node: XML element to search within
    :type node: lxml.etree._Element
    :param xpath: XPath expression to locate the target element or text
    :type xpath: str | None
    :return: Normalized text content of the first matching element or text, or None if
                no matches are found
    :rtype: str | None
    """
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
    """Extract text content from a node, excluding text from local head elements identified by the given XPath.

    :param node: XML element from which to extract text
    :type node: lxml.etree._Element
    :param head_xpath: XPath expression to identify local head elements to exclude
    :type head_xpath: str
    :return: Normalized text content of the node with local heads removed
    :rtype: str
    """
    heads_to_skip = set(node.xpath(head_xpath, namespaces=NS))
    if not heads_to_skip:
        return _normalize_ws("".join(node.itertext()))

    parts: list[str] = []
    skip_depth = 0

    for event, el in etree.iterwalk(node, events=("start", "end")):
        if event == "start":
            if skip_depth > 0:
                skip_depth += 1
            elif el in heads_to_skip:
                skip_depth = 1
            else:
                if el.text:
                    parts.append(el.text)
        else:
            if skip_depth > 0:
                skip_depth -= 1
            elif el is not node and el.tail:
                parts.append(el.tail)

    return _normalize_ws("".join(parts))


def _nearest_ancestor_head(node: etree._Element) -> str | None:
    """Find the nearest ancestor head text for a given node, searching up the tree.

    :param node: XML element for which to find the nearest ancestor head
    :type node: lxml.etree._Element
    :return: Normalized text content of the nearest ancestor head, or None if not found
    :rtype: str | None
    """
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
    """Extract text fragments from TEI XML based on a specified XPath for fragment nodes, with options for handling headings and generating stable IDs.

        :param tei_xml: TEI XML content as a string
        :type tei_xml: str
        :param fragment_xpath: XPath expression to identify fragment nodes to extract
        :type fragment_xpath: str
        :param resource_id: Optional resource ID to use in generated fragment IDs
        :type resource_id: str | None
        :param title_xpath: XPath expression to identify heading elements within fragments (default: "./tei
    :head")
        :type title_xpath: str
        :param remove_fragment_heads: Whether to remove local head text from fragment content (default:
    True)
        :type remove_fragment_heads: bool
        :param add_head_to_content: Whether to prepend the head text to the content (default
        : False)
        :type add_head_to_content: bool
        :param exclude_heads_contains: List of substrings; if any is contained in the head
        (case-insensitive), the fragment will be excluded (default: None)
        :type exclude_heads_contains: list[str] | None
        :param include_breadcrumb: Whether to include a breadcrumb field in the output with the head
        (default: True)
        :type include_breadcrumb: bool
        :param generated_id_prefix: Prefix to use for generated fragment IDs when xml:id is not
        present (default: "__DOCUMENT__")
        :type generated_id_prefix: str
        :return: List of dictionaries representing extracted fragments, each containing keys like "id",
                    "head", "content", "fragment_xpath", "fragment_index", and optionally "breadcrumb"
        :rtype: list[dict]
    """
    root = _parse_tei_xml(tei_xml)
    nodes = root.xpath(fragment_xpath, namespaces=NS)

    normalized_excludes = _normalize_patterns(exclude_heads_contains)
    fragments: list[dict] = []

    for index, node in enumerate(nodes):
        if not isinstance(node, etree._Element):
            continue

        head = _first_text_by_xpath(node, title_xpath)
        if head is None:
            head = _nearest_ancestor_head(node)

        if _should_exclude_head(head, normalized_excludes):
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
            "id": dots_id,
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
    """Extract the short identifier from a URI-like string, using '#' or '/' as delimiters.

    :param value: The input string from which to extract the short identifier (e.g. a URI)
    :type value: str | None
    :return: The extracted short identifier, or None if the input is empty or None
    :rtype: str | None
    """
    if not value:
        return None
    value = str(value)
    if "#" in value:
        return value.rsplit("#", 1)[-1]
    if "/" in value:
        return value.rstrip("/").rsplit("/", 1)[-1]
    return value


def _nav_members(nav_json) -> list[dict]:
    """Extract the list of member dictionaries from the navigation JSON structure, handling different possible nesting patterns.

    :param nav_json: The navigation JSON object from which to extract members
    :type nav_json: Any
    :return: A list of member dictionaries extracted from the navigation JSON, or an empty list
                if the expected structure is not found
    :rtype: list[dict]
    """
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
    """Extract the title from a navigation member dictionary, checking for common keys and handling different possible structures.

    :param m: The navigation member dictionary from which to extract the title
    :type m: dict
    :return: The extracted title as a string, or None if no title is found
    :rtype: str | None
    """
    dc = m.get("dublincore") or m.get("dublinCore") or {}
    if isinstance(dc, dict):
        title = dc.get("title")
        if title:
            return str(title)

    title = m.get("title")
    return str(title) if title else None


def _nav_identifier(m: dict) -> str | None:
    """Extract the identifier from a navigation member dictionary, checking for common keys and handling different possible structures.

    :param m: The navigation member dictionary from which to extract the identifier
    :type m: dict
    :return: The extracted identifier as a string, or None if no identifier is found
    :rtype: str | None
    """
    value = m.get("identifier") or m.get("@id") or m.get("id")
    return _short_id(value)


def _max_cite_depth(nav_json) -> int:
    """Determine the maximum citation depth from the navigation JSON structure, checking for common keys and handling different possible nesting patterns.

    :param nav_json: The navigation JSON object from which to determine the maximum citation depth
    :type nav_json: Any
    :return: The maximum citation depth as an integer, or 0 if it cannot be
                determined from the navigation JSON
    :rtype: int
    """
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
    """Normalize whitespace in a string by collapsing multiple spaces and trimming leading/trailing whitespace.

    :param text: The input string to normalize
    :type text: str
    :return: The input string with normalized whitespace
    :rtype: str
    """
    return " ".join((text or "").split()).strip()


def _strip_leading_head(content: str, head: str | None) -> str:
    """Remove heading prefix from content if it is duplicated at the start.

    :param content: The content string from which to remove the leading head
    :type content: str
    :param head: The head string to check for as a leading prefix in the content
    :type head: str | None
    :return: The content string with the leading head removed if it was a duplicate, otherwise
                the original content string
    :rtype: str
    """
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
    """Extract text from a node excluding descendant nodes that are separate fragments.

    :param node: The XML element from which to extract text
    :type node: lxml.etree._Element
    :param current_xml_id: The xml:id of the current fragment node being processed
    :type current_xml_id: str
    :param fragment_ids: Set of xml:id values that correspond to fragment nodes, used to
                        identify descendant fragments to exclude
    :type fragment_ids: set[str]
    :return: Normalized text content of the node with descendant fragments removed
    :rtype: str
    """
    parts: list[str] = []
    skip_depth = 0

    for event, el in etree.iterwalk(node, events=("start", "end")):
        if event == "start":
            if skip_depth > 0:
                skip_depth += 1
            else:
                xid = el.get(XML_ID)
                if xid and xid != current_xml_id and xid in fragment_ids:
                    skip_depth = 1
                else:
                    if el.text:
                        parts.append(el.text)
        else:
            if skip_depth > 0:
                skip_depth -= 1
            elif el is not node and el.tail:
                parts.append(el.tail)

    return _normalize_ws("".join(parts))


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
    """Extract the parent identifier from a navigation member dictionary, checking for common keys and handling different possible structures.

    :param m: The navigation member dictionary from which to extract the parent identifier
    :type m: dict
    :return: The extracted parent identifier as a string, or None if no parent identifier is
                found
    :rtype: str | None
    """
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
    """Normalize text for matching by collapsing whitespace, trimming, converting to lowercase, and removing diacritics.

    :param text: The input text to normalize for matching.
    :type text: str | None
    :return: The normalized text suitable for matching.
    :rtype: str
    """
    text = " ".join((text or "").split()).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _normalize_patterns(exclude_heads_contains: list[str] | None) -> list[str]:
    """Pre-normalize exclusion patterns once so per-fragment matching is a simple `in` check.

    :param exclude_heads_contains: Raw exclusion patterns.
    :type exclude_heads_contains: list[str] | None
    :return: Normalized, non-empty patterns.
    :rtype: list[str]
    """
    return [p for p in (_normalize_match_text(e) for e in (exclude_heads_contains or [])) if p]


def _should_exclude_head(head: str | None, normalized_patterns: list[str]) -> bool:
    """Determine whether a head should be excluded using pre-normalized patterns.

    :param head: The head text to check for exclusion.
    :type head: str | None
    :param normalized_patterns: Already-normalized exclusion patterns (see _normalize_patterns).
    :type normalized_patterns: list[str]
    :return: True if the head should be excluded, False otherwise.
    :rtype: bool
    """
    if not normalized_patterns:
        return False
    normalized_head = _normalize_match_text(head)
    if not normalized_head:
        return False
    return any(p in normalized_head for p in normalized_patterns)


def extract_document_text_fast(
    tei_xml: str,
    *,
    add_head_to_content: bool = True,
    exclude_heads_contains: list[str] | None = None,
    include_breadcrumb: bool = True,
) -> list[dict]:
    """Extract the full document text from TEI XML without using navigation JSON, with options for handling headings and generating a single fragment.

        :param tei_xml: TEI XML content as a string
        :type tei_xml: str
        :param add_head_to_content: Whether to include head text in the content (default:
    True)
        :type add_head_to_content: bool
        :param exclude_heads_contains: List of substrings; if any is contained in the head
        (case-insensitive), the head will be excluded from content (default: None)
        :type exclude_heads_contains: list[str] | None
        :param include_breadcrumb: Whether to include a breadcrumb field in the output with the head
        (default: True)
        :type include_breadcrumb: bool
        :return: A list containing a single dictionary representing the entire document text, with keys like
                    "id", "content", and optionally "breadcrumb"
        :rtype: list[dict]
    """
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
        "id": "__DOCUMENT__",
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
    fragment_metadata_dublincore_params: list[str] | None = None,
):
    """Extract text fragments from TEI XML using navigation JSON for structure, with options for handling headings and generating breadcrumbs.

    :param nav_json: The navigation JSON object representing the structure of the document and its fragments
    :type nav_json: Any
    :param tei_xml: TEI XML content as a string
    :type tei_xml: str
    :param add_head_to_content: Whether to include head text in the content of fragments (
    default: True)
    :type add_head_to_content: bool
    :param exclude_heads_contains: List of substrings; if any is contained in a head
    (case-insensitive), the corresponding fragment will be excluded from the results (default: None
    :type exclude_heads_contains: list[str] | None
    :param include_breadcrumb: Whether to include a breadcrumb field in the output with the head
    (default: True)
    :type include_breadcrumb: bool
    :param fragment_metadata_dublincore_params: Optional list of Dublin Core metadata keys to include in the fragment metadata (default: None)
    :type fragment_metadata_dublincore_params: dict | None
    :return: A list of dictionaries representing extracted fragments, each containing keys like "id
                "head", "content", "level", and optionally "breadcrumb"
    :rtype: list[dict]
    """
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

    normalized_excludes = _normalize_patterns(exclude_heads_contains)
    metadata_filter_frags = fragment_metadata_dublincore_params
    for m in members:
        # print("Processing member:", m)
        # sys.exit()
        mid = _nav_identifier(m)
        if not mid:
            continue

        fragment_ids.add(mid)
        nav_idx[mid] = {
            "parent": _parent_id(m),
            "title": _nav_title(m),
            "level": m.get("level"),
            # "citeType": m.get("citeType"),
            # "frag_metadata_dublincore": {k:v for k, v in m.get("dublinCore").items() if k in metadata_filter_frags},
        }
        # if mid == "art_01":
        #    print("nav_idx entry:", nav_idx[mid])

    fragments = []
    for m in members:
        xml_id = _nav_identifier(m)
        if not xml_id:
            continue

        node = xml_index.get(xml_id)
        if node is None:
            continue

        head = _nav_title(m)
        if _should_exclude_head(head, normalized_excludes):
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

        dublin_core = m.get("dublinCore") or {}

        if metadata_filter_frags is None:
            fragment_metadata_dublincore = dublin_core
        elif metadata_filter_frags:
            fragment_metadata_dublincore = {
                k: v for k, v in dublin_core.items() if k in metadata_filter_frags
            }
        else:
            fragment_metadata_dublincore = None

        fragment_title = dublin_core.get("title")

        if fragment_title is not None and head != fragment_title:
            warnings.warn(
                f"head from TEI={head!r} differs from "
                f"fragment DC:title={fragment_title!r} "
                f"for fragment identifier={xml_id!r}",
                UserWarning,
            )

        item = {
            "id": xml_id,
            "level": m.get("level"),
            "head": head,
            "content": content,
            "citeType": m.get("citeType"),
            "parent": m.get("parent"),
            "metadata_dublincore": fragment_metadata_dublincore,
        }
        if include_breadcrumb:
            item["breadcrumb"] = _breadcrumb(nav_idx, xml_id)
        fragments.append(item)
    return fragments
