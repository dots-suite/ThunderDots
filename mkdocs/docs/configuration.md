# Configuration

ThunderDots is configured through three main layers:

- client-level parameters passed to `ThunderDots(...)`;
- `collection_params`, which controls collection traversal;
- `resource_params`, which controls document fetching and fragmentation.

The defaults below reflect the current implementation in `thunderdots/client.py` and `thunderdots/config.py`.

## Client parameters

```python
from thunderdots import ThunderDots

td = ThunderDots(
    endpoint_dts="https://dots.chartes.psl.eu/api/dts",
    collection_params={"collection_id": "ENCPOS_1972"},
    resource_params={"fragment_mode": "auto"},
)
```

| Parameter | Type | Default | Role |
|---|---:|---:|---|
| `endpoint_dts` | `str` | required | DTS API root URL. Trailing `/` is removed internally. |
| `fetch_collection_metadata` | `bool` | `True` | Kept in the client configuration for collection metadata workflows. |
| `fetch_resource_metadata` | `bool` | `True` | Kept in the client configuration for resource metadata workflows. |
| `collection_params` | `dict \| None` | `None` | Collection traversal options. `None` means default `CollectionParams`. |
| `resource_params` | `dict \| None` | `None` | Resource fetching and fragmentation options. `None` means default `ResourceParams`. |
| `validate` | `bool` | `False` | Add JSON Schema validation reports to `results()["validation"]`. |
| `validation_profile` | `str` | `"dts"` | Stored in the configuration. Current automatic validation uses `output` and `resource_result` profiles. |
| `verbose` | `bool` | `True` | Enable Rich progress output. |
| `concurrency` | `int` | `20` | Number of concurrent workers for collection walking and resource fetching. |
| `timeout` | `float` | `30.0` | Legacy/global timeout value stored in the configuration. |
| `request_timeout` | `float` | `20.0` | HTTP request timeout passed to the `HttpxFetcher`. |
| `retries` | `int` | `2` | Retry attempts for temporary HTTP failures. Values are clamped by the fetcher between `0` and `5`. |
| `backoff_ms` | `int` | `200` | Base retry backoff in milliseconds. |
| `output_path` | `str \| None` | `None` | Full JSON output path. Parent directories are created automatically. |
| `cache_csv_path` | `str \| None` | `None` | Flat CSV cache/index path for fetched resources. |
| `use_cache` | `bool` | `True` | If `output_path` exists, reload it instead of running network calls. |

!!! note
    `endpoint_dts` is the only required constructor argument. If it is empty, ThunderDots raises `ValueError("endpoint_dts is required")`.

## Collection parameters

`collection_params` is converted internally to a `CollectionParams` dataclass.

```python
collection_params = {
    "collection_id": "ENCPOS_1900",
    "excluded_ids": ["COLLECTION_TO_SKIP"],
    "metadata_dublincore": ["title"],
    "metadata_extensions": [],
}
```

| Parameter | Type | Default | Role |
|---|---:|---:|---|
| `collection_id` | `str \| None` | `None` | Starting collection. `None` or an empty value starts at the DTS root collection. |
| `excluded_ids` | `list[str]` | `[]` | Collections or resources to ignore during traversal. |
| `metadata_dublincore` | `list[str] \| None` | `None` | Dublin Core collection fields to keep. `None` keeps all fields; `[]` keeps none. |
| `metadata_extensions` | `list[str] \| None` | `None` | Extension collection fields to keep. `None` keeps all fields; `[]` keeps none. |

### Metadata filtering semantics

ThunderDots intentionally distinguishes `None` from an empty list:

```python
# Keep all Dublin Core metadata and no extension metadata.
collection_params = {
    "collection_id": "ENCPOS_1972",
    "metadata_dublincore": None,
    "metadata_extensions": [],
}
```

- `None` means keep all metadata from that namespace.
- `[]` means keep no metadata from that namespace.
- `['title', 'creator']` means keep only those fields.

## Resource parameters

`resource_params` is converted internally to a `ResourceParams` dataclass.

```python
resource_params = {
    "fragment_mode": "navigation",
    "metadata_dublincore": ["title", "creator", "date"],
    "metadata_extensions": ["dct:coverage"],
    "add_head_to_content": False,
    "include_breadcrumb": True,
}
```

| Parameter | Type | Default | Role |
|---|---:|---:|---|
| `metadata_dublincore` | `list[str] \| None` | `None` | Dublin Core resource fields. `None` keeps all fields; `[]` keeps none. |
| `metadata_extensions` | `list[str] \| None` | `None` | Extension resource fields. `None` keeps all fields; `[]` keeps none. |
| `add_head_to_content` | `bool` | `True` | Add headings to extracted text. |
| `include_breadcrumb` | `bool` | `True` | Add a `breadcrumb` field to fragments when available. |
| `exclude_heads_contains` | `list[str]` | `[]` | Exclude fragments whose heading contains one of these strings. Matching is case-insensitive and accent-insensitive. |
| `fetch_document` | `bool` | `True` | Fetch `/document`. If `False`, resources are returned without text fragments. |
| `fetch_navigation` | `bool` | `True` | Fetch `/navigation` when needed by `navigation` or `auto` mode. |
| `fragment_mode` | `str` | `"auto"` | Fragmentation strategy: `auto`, `navigation`, `document`, or `tei_xpath`. |
| `fragment_xpath` | `str \| None` | `None` | TEI XPath used when `fragment_mode="tei_xpath"`. Required for `tei_xpath`. |
| `title_xpath` | `str` | `"./tei:head"` | Local heading XPath used in `tei_xpath` mode. |
| `remove_fragment_heads` | `bool` | `True` | Remove local `<head>` nodes from fragment content in `tei_xpath` mode. |
| `generated_id_prefix` | `str` | `"__DOCUMENT__"` | Prefix for generated fragment IDs when no `xml:id` is available. |

## Fragment parameters

`fragment_params` is converted internally to a `FragmentsParams` dataclass.

```
fragment_params = {
    "metadata_dublincore": ["title", "creator", "date"],
}
```

| Parameter |       Type | Default | Role |
|---|-----------:|---:|---|
| `metadata_dublincore` |`list[str]`  | `None` | Dublin Core fragment fields. `None` keeps all fields; `[]` keeps none. | 


## Fragmentation modes

### `auto`

`auto` is the default mode.

- If `fetch_navigation=True` and the resource declares `citationTrees.maxCiteDepth > 0`, ThunderDots uses `/navigation` plus `/document`.
- Otherwise, ThunderDots falls back to `document` mode.

```python
resource_params = {
    "fragment_mode": "auto",
}
```

### `document`

`document` mode fetches `/document` and returns one global fragment per resource.

```python
resource_params = {
    "fragment_mode": "document",
    "fetch_document": True,
    "fetch_navigation": False,
    "add_head_to_content": False,
}
```

Use this mode when you want one full-text record per DTS resource and plan to apply your own chunking later.

### `navigation`

`navigation` mode fetches `/navigation` and `/document`, then aligns DTS navigation identifiers with TEI `xml:id` values.

```python
resource_params = {
    "fragment_mode": "navigation",
    "fetch_document": True,
    "fetch_navigation": True,
    "add_head_to_content": False,
    "include_breadcrumb": True,
}
```

Use this mode when the endpoint exposes a reliable citation tree and you want fragments to match citable DTS identifiers.

### `tei_xpath`

`tei_xpath` mode ignores DTS navigation and fragments the TEI/XML document using your XPath expression.

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

Use this mode when you want full control over the documentary unit: one fragment per `<div>`, `<p>`, `<ab>`, or any project-specific TEI node.

## Ready-to-copy configurations

### Full document per resource

```python
td = ThunderDots(
    endpoint_dts=ENDPOINT_DTS,
    collection_params={"collection_id": COLLECTION_ID},
    resource_params={
        "fragment_mode": "document",
        "fetch_document": True,
        "fetch_navigation": False,
        "add_head_to_content": False,
        "include_breadcrumb": False,
    },
)
```

### DTS navigation fragments

```python
td = ThunderDots(
    endpoint_dts=ENDPOINT_DTS,
    collection_params={"collection_id": COLLECTION_ID},
    resource_params={
        "fragment_mode": "navigation",
        "fetch_document": True,
        "fetch_navigation": True,
        "metadata_dublincore": ["title", "creator", "date", "coverage"],
        "metadata_extensions": ["dct:coverage", "dct:extend"],
        "add_head_to_content": False,
        "include_breadcrumb": True,
        "exclude_heads_contains": [
            "index",
            "appendices",
            "annexes",
            "sources",
            "bibliographie",
            "iconographie",
        ],
    },
)
```

### TEI division fragments

```python
td = ThunderDots(
    endpoint_dts=ENDPOINT_DTS,
    collection_params={"collection_id": COLLECTION_ID},
    resource_params={
        "fragment_mode": "tei_xpath",
        "fragment_xpath": ".//tei:text/tei:body/tei:div",
        "title_xpath": "./tei:head",
        "remove_fragment_heads": True,
        "add_head_to_content": False,
        "fetch_document": True,
        "fetch_navigation": False,
        "include_breadcrumb": True,
        "generated_id_prefix": "__DOCUMENT__",
    },
)
```

## Deprecated compatibility parameter

`keep_metadata` is still accepted in both `collection_params` and `resource_params`, but it emits a `DeprecationWarning`.

```python
resource_params = {
    "keep_metadata": ["dublincore.creator", "dct:coverage", "extensions.download"],
}
```

Prefer the explicit form:

```python
resource_params = {
    "metadata_dublincore": ["creator"],
    "metadata_extensions": ["dct:coverage", "download"],
}
```
