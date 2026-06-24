# Fragmentation

ThunderDots produces a list of fragments for each resource. A fragment is the smallest unit you can send to an indexing, search, RAG, or analysis pipeline.

A minimal fragment looks like this:

```python
{
    "id": "...",
    "content": "...",
}
```

Depending on the mode, it can also include:

```python
{
    "head": "Section title",
    "breadcrumb": "Part > Chapter > Section",
    "level": 1,
    "fragment_xpath": ".//tei:text/tei:body/tei:div",
    "fragment_index": 0,
}
```

## `document`

This mode fetches `/document` and creates one global fragment per resource.

```python
resource_params = {
    "fragment_mode": "document",
    "fetch_document": True,
    "fetch_navigation": False,
    "add_head_to_content": False,
}
```

Use it when:

- you want one record per resource;
- you plan to apply your own chunking later;
- DTS navigation is absent or unsuitable.

## `navigation`

This mode uses `/navigation` plus `/document`. It aligns extracted fragments with DTS navigation identifiers.

```python
resource_params = {
    "fragment_mode": "navigation",
    "fetch_document": True,
    "fetch_navigation": True,
    "add_head_to_content": False,
    "include_breadcrumb": True,
}
```

Use it when:

- the server exposes a reliable navigation structure;
- you want fragments to match citable DTS identifiers;
- breadcrumbs are useful for a user interface.

## `tei_xpath`

This mode ignores `/navigation` and uses a user-defined XPath on the TEI/XML document.

```python
resource_params = {
    "fragment_mode": "tei_xpath",
    "fragment_xpath": ".//tei:text/tei:body/tei:div",
    "title_xpath": "./tei:head",
    "remove_fragment_heads": True,
    "add_head_to_content": False,
    "fetch_document": True,
    "fetch_navigation": False,
}
```

Use it when:

- you want one fragment per `<div>`, `<p>`, `<ab>`, or custom XML node;
- DTS navigation is too coarse or too fine;
- you need full control over documentary granularity.

## Excluding sections by heading

```python
COMMON_EXCLUDED_HEADS = [
    "index",
    "appendices",
    "annexes",
    "sources",
    "bibliographie",
    "iconographie",
    "pièces justificatives",
]
```

```python
resource_params = {
    "fragment_mode": "tei_xpath",
    "fragment_xpath": ".//tei:text/tei:body/tei:div",
    "exclude_heads_contains": COMMON_EXCLUDED_HEADS,
}
```

Matching is case-insensitive and accent-insensitive.
