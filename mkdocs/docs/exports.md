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

[Elasticsearch](https://www.elastic.co/docs/deploy-manage/deploy/self-managed/installing-elasticsearch) is a popular search engine that can index and search large volumes of text. ThunderDots can prepare payloads for bulk indexing into Elasticsearch.

> Documentation for the [`elasticsearch` Python package](https://elasticsearch-py.readthedocs.io/en/latest/).

```python
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

# Create an Elasticsearch client
es = Elasticsearch("http://localhost:9200")

# Prepare bulk indexing actions for Elasticsearch using ThunderDots
elastic_actions = td.to_elastic_actions(
    index="my_index"
)

# Perform bulk indexing
es_response = bulk(es, elastic_actions)

# Force refresh of the index to make the documents searchable immediately
es.indices.refresh(index="my_index")

# Query the index for documents containing "archives médiévales"
response = es.search(
        index="my_index",
        query={
            "match": {
                "text": "archives médiévales",
            }
        },
    )

# Display the search results
print("-| Search results |-")
for hit in response["hits"]["hits"]:
    source = hit["_source"]
    print(
            f"- {source.get('id')} | "
            f"{source.get('title')} | "
            f"score={hit.get('_score')}"
        )
```

- `to_elastic_actions()` returns bulk-style indexing actions.

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
