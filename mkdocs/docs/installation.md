# Installation

## With `uv` 

```
uv add thunderdots
```

## With `pip`

```
pip install thunderdots
```

## Local development with uv

From the repository root:

```bash
uv sync --extra dev --extra docs
```

Or through the Makefile:

```bash
make dev.sync
```

This creates or updates the local `.venv` managed by `uv` and installs the project with the development and documentation dependencies.

## Editable installation

```bash
make dev.install
```

Equivalent command:

```bash
uv pip install -e ".[dev,docs]"
```

## Documentation dependencies

Documentation dependencies are defined in `pyproject.toml` under the `docs` optional dependency group:

```toml
[project.optional-dependencies]
docs = [
    "mkdocs>=1.6.1",
    "mkdocs-material>=9.5",
    "mkdocs-jupyter>=0.25",
    "jupyter",
    "ipykernel",
]
```
