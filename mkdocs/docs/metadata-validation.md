# Metadata and validation

## Metadata filtering

ThunderDots separates Dublin Core metadata from extension metadata.

```python
resource_params = {
    "metadata_dublincore": ["identifier", "title", "creator", "date", "coverage"],
    "metadata_extensions": ["dct:coverage", "dct:extend"],
}
```

`None` keeps all metadata. An empty list `[]` keeps none.

## Temporal metadata

`DotsNotice` exposes temporal helpers derived from fields such as `date` and `coverage`.

```python
notice = td.notices()[0]
print(notice.date_start)
print(notice.date_end)
print(notice.temporal_index)
```

## Automatic validation

```python
td = ThunderDots(
    endpoint_dts=ENDPOINT_DTS,
    collection_params={"collection_id": COLLECTION_ID},
    resource_params={"fragment_mode": "document"},
    validate=True,
)

td.fetch()
print(td.results()["validation"])
```

## Manual validation

```python
from thunderdots.validation import validate_notice, validate_many

output_report = validate_notice(td.results(), profile="output")
resource_report = validate_many(
    td.results().get("resource_results", []),
    profile="resource_result",
)

print(output_report.to_dict())
print(resource_report.summary())
```

Validation checks the JSON structure. It does not guarantee the scholarly correctness of the content.
