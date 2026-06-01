# Caching and async usage

## JSON and CSV cache

ThunderDots can write two artifacts:

- `output_path`: full JSON output;
- `cache_csv_path`: flat CSV summary of resources.

```python
td = ThunderDots(
    endpoint_dts=ENDPOINT_DTS,
    collection_params={"collection_id": COLLECTION_ID},
    output_path="artifacts/thunderdots/results.json",
    cache_csv_path="artifacts/thunderdots/resources.csv",
    use_cache=True,
)

td.fetch()
```

When `use_cache=True` and `output_path` exists, ThunderDots reloads the JSON instead of running network calls again.

## Async API

ThunderDots exposes `afetch()` for notebooks and async applications.

```python
td_async = ThunderDots(
    endpoint_dts=ENDPOINT_DTS,
    collection_params={"collection_id": COLLECTION_ID},
    resource_params={"fragment_mode": "document"},
    use_cache=False,
)

await td_async.afetch()
async_results = td_async.results()
```
