# Exports

ThunderDots can transform fetched resources into practical downstream formats.

Exports are available for:

- [Python notices (basic format)](#python-notices)
- [Pandas / Polars DataFrame](#pandas--polars-dataframe)
- [Elasticsearch](#elasticsearch)
- [Qdrant](#qdrant)

## Python notices (basic format)

`td.notices()` returns one `DotsNotice` per fetched resource.

```python
notices = td.notices()
first = notices[0]

print(first.id)
print(first.title)
print(first.full_text[:500])
print(first.creator_names)
print(first.temporal_index)
```

### Metadata accessors

The example below uses the resource `ENCPOS_1900_02` of the public DoTS endpoint, fetched with `metadata_dublincore=None` and `metadata_extensions=None` (all fields kept).

```python
# Raw metadata blocks, as filtered by resource_params
first.dublincore
# {'creator': 'Jacques Boulenger', 'date': 1900, 'title': 'L’état des protestants ...'}
first.extensions.keys()
# dict_keys(['dct:coverage', 'dct:creator', 'dct:extend', 'dct:isVersionOf',
#            'dct:publisher', 'dct:rights', 'dct:source', 'download', 'html:h1'])

# Dublin Core lookups (dotted paths are accepted for nested values)
first.meta("creator")          # 'Jacques Boulenger'
first.dc("date")               # 1900
first.dc("coverage", "n/a")    # 'n/a'  -> default when the field is absent

# Extension lookups
first.ext("dct:publisher")     # 'Ecole nationale des chartes'
first.ext("dct:coverage")      # '1596/1600'

# Attribute shortcuts: any Dublin Core key, plus the parsed temporal keys
first.creator                  # 'Jacques Boulenger'
first.date                     # 1900
first.date_start               # 1900
first.date_end_iso             # '1900-12-31'
first.coverage_start           # AttributeError: no "coverage" field on this notice

# Creators as agents (from extensions) with a Dublin Core fallback
first.creator_names            # ['Jacques Boulenger']
[(agent.id, agent.name) for agent in first.creator_agents]
# [] here: dct:creator only holds identifiers on this notice, so creator_names
# falls back to dublincore.creator

# Structure
first.type                     # 'Resource'
first.linked_parents           # ['ENCPOS_1900']
len(first.fragments)           # 1 in document mode
```

The attribute shortcuts only cover Dublin Core fields and their temporal derivatives (`<field>`, `<field>_start`, `<field>_end`, `<field>_start_iso`, `<field>_end_iso`). Extension fields always go through `ext()`.

### Fragment objects

`fragment_objects()` exposes each fragment with its own metadata and temporal index (see [fragment-level metadata](metadata-validation.md#fragment-level-metadata-and-temporal-index)). The example below comes from the `cartulaires` collection of the dev endpoint, fetched with `fragment_params={"metadata_dublincore": ["title", "date"], "metadata_extensions": ["dateCreated"]}`.

```python
for fragment in first.fragment_objects():
    print(fragment.id, fragment.head, fragment.level)
    print(fragment.dublincore)      # {'title': 'IV (Septembre 1200)', 'date': '1200-09'}
    print(fragment.extensions)      # {'dateCreated': '1200-09'}
    print(fragment.breadcrumb)      # 'Cartulaire > IV (Septembre 1200)'
    print(fragment.temporal_index)
    # {'dublincore.date': '1200-09',
    #  'dublincore.date_start': 1200, 'dublincore.date_start_iso': '1200-09-01',
    #  'dublincore.date_end': 1200,   'dublincore.date_end_iso': '1200-09-30',
    #  'extensions.dateCreated': '1200-09', ...}
    print(fragment.content[:200])
```

`fragment.temporal_index` returns `{}` for a fragment without explicit date, and `fragment.raw` gives the original dictionary.

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
- `to_elastic_documents()` returns the same documents without the bulk envelope.

### Document structure

Each Elasticsearch document holds the resource metadata at the top level and, when `include_fragments=True` (default), the list of fragments with their own `metadata` and `temporal` blocks. The example below was built from a cartulaire fetched with:

```python
resource_params={
    "fragment_mode": "navigation",
    "metadata_dublincore": ["title", "creator", "coverage"],
    "metadata_extensions": ["temporalCoverage"],
},
fragment_params={
    "metadata_dublincore": ["title", "date"],
    "temporal_xpath": ".//tei:docDate/tei:date",
},
```

```json
{
  "id": "CART_SAMPLE",
  "type": "Resource",
  "title": "Cartulaire de test",
  "text": "Cartulaire de test (1157-1185) ...",
  "dublincore": {"title": "Cartulaire de test", "creator": "Éditeur de test", "coverage": "1157/1185"},
  "extensions": {"temporalCoverage": "1157/1185"},
  "temporal": {
    "dublincore.coverage": "1157/1185",
    "dublincore.coverage_start": 1157,
    "dublincore.coverage_start_iso": "1157-01-01",
    "dublincore.coverage_end": 1185,
    "dublincore.coverage_end_iso": "1185-12-31",
    "extensions.temporalCoverage_start": 1157,
    "extensions.temporalCoverage_end": 1185
  },
  "creator_names": ["Éditeur de test"],
  "linked_parents": ["CART_SAMPLE_COLL"],
  "metadata_flat": {
    "dublincore.creator": "Éditeur de test",
    "extensions.temporalCoverage": "1157/1185",
    "temporal.dublincore.coverage_start": 1157
  },
  "fragments": [
    {
      "id": "CART_SAMPLE_0002",
      "level": 2,
      "head": "Sentence arbitrale.",
      "breadcrumb": "Actes > Sentence arbitrale.",
      "content": "Sentence arbitrale d ...",
      "metadata": {
        "dublincore": {"title": "Sentence arbitrale.", "date": "1173-05-02"},
        "tei": {"date": "1173-05-02"}
      },
      "temporal": {
        "dublincore.date_start": 1173,
        "dublincore.date_start_iso": "1173-05-02",
        "dublincore.date_end_iso": "1173-05-02",
        "tei.date_start": 1173,
        "tei.date_end": 1173
      }
    }
  ]
}
```

| Field | Content |
|---|---|
| `dublincore`, `extensions` | Resource metadata, as filtered by `resource_params`. |
| `temporal` | Resource temporal index (`<field>_start`, `<field>_end`, `<field>_start_iso`, `<field>_end_iso`). |
| `metadata_flat` | `dublincore`, `extensions` and `temporal` flattened with dotted keys, convenient for keyword fields. |
| `fragments[].metadata` | Fragment metadata (`dublincore`, `extensions`, `tei`), as filtered by `fragment_params`. |
| `fragments[].temporal` | Fragment temporal index, computed from the fragment metadata only (`{}` when the fragment has no explicit date). Present when `fragment_params` is given. |

### Reading resource and fragment metadata from a hit

```python
response = es.search(index="my_index", query={"match": {"text": "sentence arbitrale"}})

for hit in response["hits"]["hits"]:
    source = hit["_source"]

    # Resource-level metadata
    creator = source["dublincore"].get("creator")                 # 'Éditeur de test'
    coverage = source["extensions"].get("temporalCoverage")        # '1157/1185'
    start = source["temporal"].get("dublincore.coverage_start")    # 1157
    end_iso = source["temporal"].get("dublincore.coverage_end_iso")  # '1185-12-31'
    flat_creator = source["metadata_flat"].get("dublincore.creator")

    # Fragment-level metadata
    for fragment in source.get("fragments", []):
        title = fragment["metadata"].get("dublincore", {}).get("title")
        tei_date = fragment["metadata"].get("tei", {}).get("date")   # '1173-05-02'
        temporal = fragment.get("temporal") or {}
        year = temporal.get("tei.date_start")                        # 1173
        print(fragment["id"], title, tei_date, year, fragment["breadcrumb"])
```

### Filtering on dates

Elasticsearch expands dotted keys into objects, so `temporal["dublincore.coverage_start"]` is addressed as the field path `temporal.dublincore.coverage_start`. A resource-level range filter needs no special mapping:

```python
response = es.search(
    index="my_index",
    query={
        "bool": {
            "must": {"match": {"text": "donation"}},
            "filter": {"range": {"temporal.dublincore.coverage_start": {"gte": 1150, "lte": 1200}}},
        }
    },
)
```

To filter on **fragment** dates, map `fragments` as `nested` before indexing. Otherwise Elasticsearch flattens the array and a query could match the date of one fragment with the text of another:

```python
es.indices.create(
    index="my_index",
    mappings={
        "properties": {
            "fragments": {
                "type": "nested",
                "properties": {
                    "content": {"type": "text"},
                    "temporal": {
                        "properties": {
                            "tei": {"properties": {"date_start": {"type": "integer"}, "date_end": {"type": "integer"}}},
                            "dublincore": {"properties": {"date_start": {"type": "integer"}, "date_end": {"type": "integer"}}},
                        }
                    },
                },
            }
        }
    },
)

response = es.search(
    index="my_index",
    query={
        "nested": {
            "path": "fragments",
            "query": {
                "bool": {
                    "must": {"match": {"fragments.content": "donation"}},
                    "filter": {"range": {"fragments.temporal.tei.date_start": {"gte": 1150, "lte": 1200}}},
                }
            },
            "inner_hits": {"_source": ["fragments.id", "fragments.head", "fragments.metadata", "fragments.temporal"]},
        }
    },
)

for hit in response["hits"]["hits"]:
    for inner in hit["inner_hits"]["fragments"]["hits"]["hits"]:
        fragment = inner["_source"]
        print(hit["_source"]["id"], fragment["id"], fragment["temporal"].get("tei.date_start"))
```

`inner_hits` returns only the fragments that matched, with their metadata, instead of the whole resource. Use `to_elastic_actions(include_fragments=False)` when you index fragments separately, for example through the Qdrant fragment export below or your own [custom fragment records](#custom-fragment-records).

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

### One point per fragment

For chunk-level retrieval, ThunderDots can also emit one Qdrant point per non-empty fragment. Each payload carries the fragment text, its own `metadata` and `temporal` index (see [fragment-level metadata](metadata-validation.md#fragment-level-metadata-and-temporal-index)), and the `record_id` of its resource. Point identifiers are stable hashes of `"<resource id>::<fragment id>"`.

```python
payloads = td.to_qdrant_fragment_payloads()

vectors = [[0.0] * 384 for _ in payloads]
points = td.to_qdrant_fragment_points(
    vectors=vectors,
    include_resource_temporal=True,   # adds resource dates under "resource_temporal"
)
```

Fragment payloads expose flattened, sanitized keys ready for filtering, for example `temporal__tei__date_start` or `resource_temporal__dublincore__coverage_start`. Resource-level dates are only present when `include_resource_temporal=True`, under their own namespace, so the provenance of every date stays explicit.



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
