<h1 align="center">
  <img src="assets/dots-light.png" width="450"><br>
  ThunderDoTS — DTS Crawler via <img src="assets/dots-logo-retro.drawio.png" height="40">
</h1>




[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![ruff](https://img.shields.io/badge/lint-ruff-0A0A0A?logo=ruff&logoColor=white)](https://img.shields.io/badge/lint-ruff-0A0A0A?logo=ruff&logoColor=white)

## Features

- Ultra-fast DTS crawling via engines: Python Asyncio or Go concurrency
- Collection & resource traversal (Depth-First Search walk method)
- TEI fragment extraction aligned with citation trees
- Simple Python API
- Configurable timeouts, retries, concurrency

## Quickstart

```Python
from thunderdots import ThunderDots

td = ThunderDots(
    endpoint_dts="https://dev.chartes.psl.eu/dots/api/dts",
    collection_params={"collection_id": "ENCPOS"},
    engine="python", # or "go" for Go native extension
)

td.fetch()

print(td.stats())
```


## Installation

### Via uv 

```bash
uv pip install thunderdots
```

### Via pip

```bash
pip install thunderdots
```

### For development

Clone the repo and install in editable mode:

```bash
git clone 
cd ThunderDots/
```

With [uv](https://docs.astral.sh/uv/getting-started/):

```bash
uv venv
source .venv/bin/activate
uv pip install -e .
```

With pip:

```bash
pip install -e .
```

## Build Go native extension (optional, dev only)

```bash
cd thunderdots/native/go

# MacOS
go build -buildmode=c-shared -o ../build/libthunderdots.dylib ./cmd/thunderdots
# Linux
go build -buildmode=c-shared -o ../build/libthunderdots.so ./cmd/thunderdots
# Windows
go build -buildmode=c-shared -o ../build/libthunderdots.dll ./cmd/thunderdots
```

## Lint via ruff

```bash
ruff check thunderdots
```

## Architecture 


```
                    ThunderDots (Python API)
                            │
                            ▼
                Orchestrateur async (asyncio)
          (walk_collections + fetch_resources + build_output)
                            │
                            ▼
                    Fetcher interface
                            │
            ┌───────────────┴────────────────┐
            │                                │
            ▼                                ▼
      HttpxFetcher (Python)              GoFetcher (Go)
   httpx.AsyncClient + retries           ctypes + libthunderdots
   limits/max_connections                (TDGetJSON / TDGetText)
            │                                │
            └───────────────┬────────────────┘
                            ▼
                        DTS HTTP API
                (/collection /navigation /document)
                            │
                            ▼
                        TEI XML (doc)
                            │
                            ▼
                   TEI extraction (lxml)
            ┌────────────────┴────────────────┐
            │                                 │
            ▼                                 ▼
   Fast path (maxCiteDepth=0)         Slow path (maxCiteDepth>0)
 extract_document_text_fast()         extract_fragments(nav, xml)
 (pas d’index xml:id)                (index xml:id + breadcrumbs)
```



## License

...

## Citation

...
