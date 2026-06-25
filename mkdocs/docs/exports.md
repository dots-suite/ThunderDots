# Exports

ThunderDots can transform fetched resources into practical downstream formats.

Exports are available for:

- [Python notices (basic format)](#python-notices)
- [Pandas / Polars DataFrame](#pandas--polars-dataframe)
- [Elasticsearch](#elasticsearch)
- [Qdrant](#qdrant)

## Python notices (basic format)

```python
notices = td.notices()
first = notices[0]

print(first.id)
print(first.title)
print(first.full_text[:500])
print(first.creator_names)
print(first.temporal_index)
```

## Pandas / Polars DataFrame

ThunderDots can export all fetched resources into a flat DataFrame — one row per resource — with no extra dependencies beyond your chosen backend.

### Installation

```bash
uv install pandas      # for backend="pandas" or use pip install pandas
uv install polars      # for backend="polars" or use pip install polars
```

### Basic usage

```python
# Pandas (default)
df = td.to_dataframe()

# Polars
df = td.to_dataframe(backend="polars")
```

All columns are included by default.  The flat schema contains:

| Column | Description |
|---|---|
| `id` | DTS resource identifier |
| `type` | Resource type |
| `title` | Resource title |
| `linked_parents` | List of parent collection IDs |
| `fragments_count` | Number of text fragments |
| `text` | Full text (all fragments joined) |
| `dublincore.<key>` | Dublin Core metadata fields, flattened |
| `extensions.<key>` | Extension metadata fields, flattened |

### Column mapping

Use `column_map` to **select and rename** columns in one step.  Only the listed columns appear in the output:

```python
df = td.to_dataframe(
    backend="polars",
    column_map={
        "id":                   "resource_id",
        "title":                "title",
        "dublincore.creator":   "author",
        "dublincore.date":      "year",
        "text":                 "full_text",
    },
)
print(df)
```

```
shape: (3, 5)
┌──────────────────┬───────────────────────────────────┬───────────────────┬──────┬──────────────────────────────────────┐
│ resource_id      ┆ title                             ┆ author            ┆ year ┆ full_text                            │
│ ---              ┆ ---                               ┆ ---               ┆ ---  ┆ ---                                  │
│ str              ┆ str                               ┆ str               ┆ str  ┆ str                                  │
╞══════════════════╪═══════════════════════════════════╪═══════════════════╪══════╪══════════════════════════════════════╡
│ ENCPOS_1972_01   ┆ Les archives de l'abbaye…         ┆ Dupont, Jean      ┆ 1972 ┆ L'abbaye de Saint-Denis conserve…    │
│ ENCPOS_1972_02   ┆ Étude sur le cartulaire…          ┆ Martin, Claire    ┆ 1972 ┆ Le cartulaire de Marmoutier…         │
│ ENCPOS_1972_03   ┆ La chancellerie royale…           ┆ Bernard, Pierre   ┆ 1972 ┆ La chancellerie sous Philippe IV…    │
└──────────────────┴───────────────────────────────────┴───────────────────┴──────┴──────────────────────────────────────┘
```

### Records without a DataFrame library

`to_records()` returns the same flat data as a plain `list[dict]`, with no external dependency:

```python
records = td.to_records(
    column_map={
        "id":                 "resource_id",
        "dublincore.creator": "author",
        "dublincore.date":    "year",
    },
)
# [{'resource_id': 'ENCPOS_1972_01', 'author': 'Dupont, Jean', 'year': '1972'}, ...]
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
