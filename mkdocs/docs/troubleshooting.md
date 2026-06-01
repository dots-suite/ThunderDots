# Troubleshooting

| Symptom | Possible cause | Solution |
|---|---|---|
| `resource_results` is empty | Wrong `collection_id` or unreachable endpoint | Test `/collection?id=...` in a browser or with curl |
| Empty fragments | Unexpected XML or wrong XPath | Inspect the XML returned by `/document` |
| One fragment despite `navigation` | No citation tree or missing navigation | Use `tei_xpath` |
| Headings appear in content | `add_head_to_content=True` or global extraction | Set `add_head_to_content=False` |
| Unwanted sections are indexed | Head filters are too weak | Extend `exclude_heads_contains` |
| Many generated IDs | TEI nodes have no `xml:id` | Add `xml:id` values or accept stable SHA1 IDs |
| Online tests fail | Endpoint changed or network unavailable | Run offline tests first; keep online tests optional |

## Online tests

Online tests are intentionally opt-in:

```bash
RUN_NETWORK_TESTS=1 pytest
```

Offline tests run by default:

```bash
pytest
```
