# Exports

ThunderDots can transform fetched resources into practical downstream formats.

## Python notices

```python
notices = td.notices()
first = notices[0]

print(first.id)
print(first.title)
print(first.full_text[:500])
print(first.creator_names)
print(first.temporal_index)
```

## Elasticsearch

```python
elastic_docs = td.to_elastic_documents(
    include_fragments=True,
    include_raw=False,
)

elastic_actions = td.to_elastic_actions(
    index="my_index",
    include_fragments=False,
    include_raw=False,
)
```

`to_elastic_documents()` returns plain dictionaries. `to_elastic_actions()` returns bulk-style indexing actions.

## Qdrant

ThunderDots prepares payloads and points, but does not generate embeddings.

```python
payloads = td.to_qdrant_payloads(
    include_fragments=True,
    include_raw=False,
)

vectors = [[0.0] * 384 for _ in payloads]
points = td.to_qdrant_points(
    vectors=vectors,
    include_fragments=True,
    include_raw=False,
)
```

If the number of vectors does not match the number of notices, ThunderDots raises a `ValueError`.

## Custom fragment records

```python
def iter_fragment_documents(results: dict):
    for resource in results.get("resource_results", []):
        resource_id = resource.get("id")
        title = resource.get("title")
        metadata = resource.get("metadata") or {}
        linked_parents = resource.get("linked_parents") or []

        for index, fragment in enumerate(resource.get("fragments", [])):
            content = (fragment.get("content") or "").strip()
            if not content:
                continue

            yield {
                "id": f"{resource_id}__frag_{index}",
                "record_id": resource_id,
                "id": fragment.get("id"),
                "title": title,
                "head": fragment.get("head"),
                "breadcrumb": fragment.get("breadcrumb"),
                "text": content,
                "metadata": metadata,
                "linked_parents": linked_parents,
            }
```
