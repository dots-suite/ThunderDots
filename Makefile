.PHONY: help \
	dev.sync dev.install \
	docs.prepare docs.serve docs.build docs.build-dev docs.clean docs.check docs.deploy \
	tests.unit tests.network tests.all \
	lint.check lint.format \
	check clean

# ---------------------------------------------------------------------
# Tooling
# ---------------------------------------------------------------------

UV ?= uv
PYTHON ?= $(UV) run python
PYTEST ?= $(PYTHON) -m pytest
RUFF ?= $(PYTHON) -m ruff
MKDOCS ?= $(PYTHON) -m mkdocs

# ---------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------

DOCS_DIR ?= mkdocs
DOCS_CONFIG ?= $(DOCS_DIR)/mkdocs.yml
DOCS_SRC ?= $(DOCS_DIR)/docs
DOCS_SITE ?= $(DOCS_DIR)/site

ROOT_ASSETS_DIR ?= assets
DOCS_ASSETS_DIR ?= $(DOCS_SRC)/assets

NOTEBOOKS_DIR ?= notebooks
DOCS_NOTEBOOKS_DIR ?= $(DOCS_SRC)/notebooks
USER_NOTEBOOK ?= thunderdots_documentation_utilisateur.ipynb

# ---------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------

help:
	@echo "ThunderDots development commands"
	@echo ""
	@echo "Environment:"
	@echo "  make dev.sync          Sync project dependencies with uv"
	@echo "  make dev.install       Install project with dev and docs extras"
	@echo ""
	@echo "Documentation:"
	@echo "  make docs.prepare      Copy assets and notebooks into MkDocs docs_dir"
	@echo "  make docs.serve        Serve MkDocs locally"
	@echo "  make docs.build        Build documentation in strict mode"
	@echo "  make docs.build-dev    Build documentation without strict mode"
	@echo "  make docs.check        Validate documentation build"
	@echo "  make docs.deploy       Deploy documentation to gh-pages"
	@echo "  make docs.clean        Remove generated documentation site"
	@echo ""
	@echo "Tests:"
	@echo "  make tests.unit        Run unit tests without network tests"
	@echo "  make tests.network     Run tests with online DTS tests"
	@echo "  make tests.all         Run all tests"
	@echo ""
	@echo "Linting:"
	@echo "  make lint.check        Run Ruff checks"
	@echo "  make lint.format       Format code with Ruff"
	@echo ""
	@echo "Global:"
	@echo "  make check             Run lint + tests + docs check"
	@echo "  make clean             Remove generated caches and build artefacts"

# ---------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------

dev.sync:
	$(UV) sync --extra dev --extra docs

dev.install:
	$(UV) pip install -e ".[dev,docs]"

# ---------------------------------------------------------------------
# Documentation
# ---------------------------------------------------------------------

docs.prepare:
	mkdir -p $(DOCS_ASSETS_DIR)
	mkdir -p $(DOCS_NOTEBOOKS_DIR)
	@if [ -d "$(ROOT_ASSETS_DIR)" ]; then \
		cp -R $(ROOT_ASSETS_DIR)/* $(DOCS_ASSETS_DIR)/ 2>/dev/null || true; \
	fi
	@if [ -f "$(NOTEBOOKS_DIR)/$(USER_NOTEBOOK)" ]; then \
		cp "$(NOTEBOOKS_DIR)/$(USER_NOTEBOOK)" "$(DOCS_NOTEBOOKS_DIR)/$(USER_NOTEBOOK)"; \
	fi

docs.serve: docs.prepare
	$(MKDOCS) serve -f $(DOCS_CONFIG)

docs.build: docs.prepare
	$(MKDOCS) build -f $(DOCS_CONFIG) --strict

docs.build-dev: docs.prepare
	$(MKDOCS) build -f $(DOCS_CONFIG)

docs.clean:
	rm -rf $(DOCS_SITE)

docs.check: docs.build

docs.deploy: docs.prepare
	$(MKDOCS) gh-deploy -f $(DOCS_CONFIG) --force

# ---------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------

tests.unit:
	$(PYTEST)

tests.network:
	RUN_NETWORK_TESTS=1 $(PYTEST)

tests.all: tests.network

# ---------------------------------------------------------------------
# Linting / formatting
# ---------------------------------------------------------------------

lint.check:
	$(RUFF) check thunderdots tests

lint.format:
	$(RUFF) format thunderdots tests
	$(RUFF) check thunderdots tests --fix

# ---------------------------------------------------------------------
# Global checks
# ---------------------------------------------------------------------

check: lint.check tests.unit docs.check

# ---------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------

clean: docs.clean
	rm -rf .pytest_cache
	rm -rf .ruff_cache
	rm -rf htmlcov
	rm -rf dist
	rm -rf build
	rm -rf *.egg-info
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
