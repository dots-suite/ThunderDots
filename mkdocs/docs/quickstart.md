# Quick start

## 1. Configure an endpoint and a collection

A DTS endpoint usually exposes routes such as `/collection`, `/document`, and `/navigation`. ThunderDots only needs the DTS API root.

```python
ENDPOINT_DTS = "https://dots.chartes.psl.eu/api/dts"
COLLECTION_ID = "ENCPOS_1900" # or "ENCPOS"
```

## 2. Fetch a collection

```python
from thunderdots import ThunderDots

td = ThunderDots(
    endpoint_dts=ENDPOINT_DTS,
    collection_params={
        "collection_id": COLLECTION_ID,
        "metadata_dublincore": ["title"],
    },
    resource_params={
        "fragment_mode": "document",
        "metadata_dublincore": ["title", "creator", "date", "coverage"],
    },
    verbose=True,
    use_cache=False,
)

td.fetch()
results = td.results()
```

## 3. Inspect results

```python
print(results.keys())
print(len(results.get("collection_results", [])))
print(len(results.get("resource_results", [])))
print(td.stats())
```

The output has this general structure:

```python
{
    "dtsVersion": "1-alpha",
    "type": "All",
    "meta": {...},
    "collection_results": [...],
    "resource_results": [...],
}
```

Each resource result contains metadata and fragments:

```python
{
    "id": "ENCPOS_1900_01",
    "@type": "Resource",
    "title": "...",
    "linked_parents": [...],
    "metadata": {...},
    "fragments": [...],
}
```
