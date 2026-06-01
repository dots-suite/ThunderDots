# ThunderDots

ThunderDots is a Python client for [DTS](https://dtsapi.org/specifications/) (*Distributed Text Services*) endpoints, initially built for [DoTS](https://chartes.github.io/dots_documentation/).

It helps you move from a remote DTS API to structured Python objects and JSON records that can feed indexing pipelines (including full-text search, RAG-vector databases) or corpus-analysis workflows.

## What ThunderDots does

ThunderDots can:

- walk DTS collections and subcollections;
- fetch resources and TEI/XML documents;
- extract text fragments from documents, DTS navigation, or custom TEI XPath rules;
- preserve or filter Dublin Core and extension metadata;
- validate generated outputs;
- export records to indexation pipelines (like Elasticsearch or Qdrant-compatible formats);
- cache fetched corpora as JSON and CSV.

## Installation 

With `uv` 

```
uv add thunderdots
```

With `pip`

```
pip install thunderdots
```

## Minimal example

```python
from thunderdots import ThunderDots

td = ThunderDots(
    endpoint_dts="https://dev.chartes.psl.eu/dots/api/dts",
    collection_params={"collection_id": "ENCPOS_1900"},
    resource_params={"fragment_mode": "document"},
)

td.fetch()
results = td.results()
```

## License

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/chartes/thunderdots/blob/master/LICENSE.md)

## Citation

```
@software{terriel_thunderdots_2026,
  author       = {Terriel, Lucas},
  title        = {ThunderDots},
  year         = {2026},
  publisher    = {GitHub},
  url          = {https://github.com/chartes/thunderdots},
  note         = {Python client for Distributed Text Services endpoints via DoTS}
}
```