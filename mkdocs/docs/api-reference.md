# API reference

This page summarizes the public API exposed by ThunderDots.

## `ThunderDots`

```python
from thunderdots import ThunderDots
```

### Constructor

```python
ThunderDots(
    endpoint_dts: str,
    collection_params: dict | None = None,
    resource_params: dict | None = None,
    validate: bool = False,
    verbose: bool = True,
    concurrency: int = 20,
    request_timeout: float = 20.0,
    retries: int = 2,
    backoff_ms: int = 200,
    output_path: str | None = None,
    cache_csv_path: str | None = None,
    use_cache: bool = True,
)
```

### Fetching

```python
td.fetch()
await td.afetch()
```

### Results

```python
td.results()
td.collection_results()
td.resource_results()
td.stats()
```

### Object conversion

```python
td.notices()
```

### Exports

```python
td.to_elastic_documents(include_fragments=True, include_raw=False)
td.to_elastic_actions(index="my_index", include_fragments=True, include_raw=False)
td.to_qdrant_payloads(include_fragments=True, include_raw=False)
td.to_qdrant_points(vectors=vectors, include_fragments=True, include_raw=False)
```

## Validation helpers

```python
from thunderdots.validation import validate_notice, validate_many
```

```python
validate_notice(data, profile="output")
validate_many(items, profile="resource_result")
```
