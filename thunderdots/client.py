# -*- coding: utf-8 -*-

"""client.py

ThunderDots client interface (single Python pipeline, optional Go fetcher).
"""

from __future__ import annotations

import concurrent.futures
import threading
import asyncio
import csv
import json
from pathlib import Path
from typing import Any

from .ui import UI
from .stats import Stats
from .config import ThunderDotsConfig, CollectionParams, ResourceParams, FragmentsParams
from .fetcher import HttpxFetcher, Fetcher
from .extract.walker import walk_collections
from .extract.resources import fetch_resources
from .normalize.output import build_output
from .normalize.metadata import canonicalize_metadata_keys
from .validation import validate_notice, validate_many
from .orm import DotsNotice
from importlib.metadata import PackageNotFoundError, version


def _package_version() -> str:
    """Return the installed ThunderDots package version.

    :return: Installed package version, or ``"0.0.0"`` when package metadata is unavailable.
    :rtype: str
    """
    try:
        return version("thunderdots")
    except PackageNotFoundError:
        return "0.0.0"


def _run_coro_in_thread(coro_factory: callable[[], Any]) -> Any:
    """Run an async coroutine in a separate thread and return its result, allowing async code to run in sync contexts (e.g. notebooks).

    :param coro_factory: A callable that returns the coroutine to run (e.g. a lambda that calls an async method).
    :type coro_factory: callable[[], Any]
    :return: The result of the coroutine once it has completed.
    :rtype: Any
    """
    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def runner() -> None:
        """Run the coroutine and store the result or any exception that occurs."""
        try:
            result["value"] = asyncio.run(coro_factory())
        except BaseException as exc:
            error["value"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()

    if "value" in error:
        raise error["value"]

    return result.get("value")


def _flatten_for_csv(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    """Flatten a nested dictionary into a flat dictionary with dot-separated keys, suitable for CSV output. Lists are JSON-encoded, and None values become empty strings.

    :param data: The input dictionary to flatten, which may contain nested dictionaries and lists.
    :type data: dict[str, Any]
    :param prefix: The prefix to prepend to keys (used for recursion, default is empty
    string).
    :type prefix: str, optional
    :return: A flat dictionary with dot-separated keys and string values, suitable for CSV output
    :rtype: dict[str, str]
    """
    out: dict[str, str] = {}

    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key

        if isinstance(value, dict):
            out.update(_flatten_for_csv(value, full_key))
        elif isinstance(value, list):
            out[full_key] = json.dumps(value, ensure_ascii=False)
        elif value is None:
            out[full_key] = ""
        else:
            out[full_key] = str(value)

    return out


class ThunderDots:
    """Client class for fetching and processing data from a DTS endpoint, with support for configuration, caching, and result output."""

    def __init__(
        self,
        endpoint_dts: str,
        fetch_collection_metadata: bool = True,
        fetch_resource_metadata: bool = True,
        collection_params: dict[str, Any] | None = None,
        resource_params: dict[str, Any] | None = None,
        fragment_params: dict[str, Any] | None = None,
        validate: bool = False,
        validation_profile: str = "dts",
        verbose: bool = True,
        concurrency: int = 20,
        timeout: float = 30.0,
        request_timeout: float = 20.0,
        retries: int = 2,
        backoff_ms: int = 200,
        output_path: str | None = None,
        cache_csv_path: str | None = None,
        use_cache: bool = True,
    ) -> None:
        """Initialize ThunderDots client with configuration parameters.

        :param endpoint_dts: Base URL of the DTS endpoint (e.g. "https://example.com/dts").
        :type endpoint_dts: str
        :param fetch_collection_metadata: Whether to fetch metadata for collections (default: True).
        :type fetch_collection_metadata: bool
        :param fetch_resource_metadata: Whether to fetch metadata for resources (default: True).
        :type fetch_resource_metadata: bool
        :param collection_params: Dictionary of parameters for collection fetching/filtering (default: None).
        :type collection_params: dict[str, Any] | None
        :param resource_params: Dictionary of parameters for resource fetching/filtering (default: None).
        :type resource_params: dict[str, Any] | None
        :param fragment_params: Dictionary of parameters for fragment fetching/filtering (default: None).
        :type fragment_params: dict[str, Any] | None
        :param verbose: Whether to enable verbose logging and UI (default: True).
        :type verbose: bool
        :param concurrency: Number of concurrent fetches for Python fetcher (default: 20
        :type concurrency: int
        :param timeout: Request timeout in seconds for Python fetcher (default: 30.
        :type timeout: float
        :param retries: Number of retries for failed requests (default: 2).
        :type retries: int
        :param backoff_ms: Base backoff in milliseconds for retries (default: 200
                            ms).
        :type backoff_ms: int
        :param output_path: Optional path to save the final output JSON (e.g. "
                            output/results.json"), if not provided results will not be saved to disk (default: None).
        :type output_path: str | None
        :raises ValueError: If endpoint_dts is not provided or if fetcher is not "python" or "go".
        """

        endpoint = (endpoint_dts or "").rstrip("/")

        if not endpoint:
            raise ValueError("endpoint_dts is required")

        self.config = ThunderDotsConfig(
            endpoint_dts=endpoint,
            fetch_collection_metadata=fetch_collection_metadata,
            fetch_resource_metadata=fetch_resource_metadata,
            validate=validate,
            validation_profile=validation_profile,
            collection_params=CollectionParams.from_dict(collection_params),
            resource_params=ResourceParams.from_dict(resource_params),
            fragment_params=FragmentsParams.from_dict(fragment_params),
            verbose=verbose,
            concurrency=int(concurrency),
            timeout=float(timeout),
            request_timeout=float(request_timeout),
            retries=int(retries),
            backoff_ms=int(backoff_ms),
            output_path=output_path,
            cache_csv_path=cache_csv_path,
            use_cache=bool(use_cache),
        )

        self._stats = Stats()

        self._results: dict[str, Any] | None = None

        self._executor: concurrent.futures.ThreadPoolExecutor | None = None

    # ---------------- PUBLIC API ---------------- #

    def _validate_results_if_needed(self) -> None:
        """Validate current results when validation is enabled.

        This method enriches the current result dictionary with validation
        reports. It is used both after a fresh fetch and after loading results
        from cache.

        :return: None.
        :rtype: None
        """
        if not self.config.validate:
            return

        if not isinstance(self._results, dict):
            return

        output_report = validate_notice(self._results, profile="output")

        resource_report = validate_many(
            self._results.get("resource_results", []),
            profile="resource_result",
        )

        self._results["validation"] = {
            "output": output_report.to_dict(),
            "resources": resource_report.summary(),
        }

    async def afetch(self) -> None:
        """Fetch data asynchronously from the DTS endpoint.

        If cache loading is enabled and a cached result exists, the cached
        output is loaded and optionally validated before returning.

        :return: None.
        :rtype: None
        """
        if self._load_results_from_cache():
            self._validate_results_if_needed()
            return

        await self._async_fetch()

    def fetch(self) -> None:
        """Fetch collections and resources from the DTS endpoint and build results.

        This method runs the main fetching and processing pipeline, which includes:
        - Walking collections starting from the specified collection_id, applying exclusions and metadata fetching as configured.
        - Fetching resources linked from the collections, applying metadata fetching and filtering as configured.
        - Building the final results dictionary with collection and resource results, along with stats and version info
        - Optionally saving the results to a JSON file if output_path is configured.
        """
        if self._load_results_from_cache():
            self._validate_results_if_needed()
            return

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self._async_fetch())
            return

        _run_coro_in_thread(self._async_fetch)

    def results(self) -> dict[str, Any]:
        """Get the results of the fetch operation, including collection and resource results, stats, and version info.

        :return: A dictionary containing the results of the fetch operation, with keys "dtsVersion", "type", "meta", "collection_results", and "resource_results". If fetch has not been called yet, returns an empty dictionary.
        :rtype: dict[str, Any]
        """
        return self._results or {}

    def collection_results(self) -> dict[str, Any]:
        """Get only the collection results from the fetch operation.

        :return: A dictionary containing the collection results, with keys "dtsVersion", "type", and "collection_results". If fetch has not been called yet, returns an empty dictionary.
        :rtype: dict[str, Any]
        """
        return {
            "dtsVersion": "1-alpha",
            "type": "Collection",
            "collection_results": self.results().get("collection_results", []),
        }

    def resource_results(self) -> dict[str, Any]:
        """Get only the resource results from the fetch operation.

        :return: A dictionary containing the resource results, with keys "dtsVersion", "type", and "resource_results". If fetch has not been called yet, returns an empty dictionary.
        :rtype: dict[str, Any]
        """
        return {
            "dtsVersion": "1-alpha",
            "type": "Resource",
            "resource_results": self.results().get("resource_results", []),
        }

    def stats(self) -> dict[str, Any]:
        """Get the statistics collected during the fetch operation.

        :return: A dictionary containing the statistics collected during the fetch operation, such as counts of collections and resources fetched, HTTP errors, and timing information. If fetch has not been called yet, returns an empty dictionary.
        :rtype: dict[str, Any]
        """
        return self._stats.to_dict()

    def _write_results_if_needed(self) -> None:
        """Write the results to a JSON file if output_path is configured.
        If output_path is not set, this method does nothing. If output_path is set, it ensures the parent directory exists and writes the results of the fetch operation to the specified file in JSON format with UTF-8 encoding.
        """
        if not self.config.output_path:
            return
        p = Path(self.config.output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.results(), ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------------- INTERNAL ---------------- #

    def _load_results_from_cache(self) -> bool:
        """Load cached JSON results if enabled and available."""
        if not self.config.use_cache:
            return False
        if not self.config.output_path:
            return False

        p = Path(self.config.output_path)
        if not p.exists():
            return False

        try:
            self._results = json.loads(p.read_text(encoding="utf-8"))
            return isinstance(self._results, dict)
        except Exception:
            self._results = None
            return False

    def _write_cache_csv_if_needed(self) -> None:
        """Write a flat CSV cache/index for fetched resources."""
        if not self.config.cache_csv_path:
            return

        results = self.results()
        resources = results.get("resource_results", [])
        if not isinstance(resources, list):
            return

        path = Path(self.config.cache_csv_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        flattened_rows: list[dict[str, str]] = []
        dynamic_fields: set[str] = set()

        for resource in resources:
            metadata = canonicalize_metadata_keys(resource.get("metadata") or {})
            fragments = resource.get("fragments") or []

            text_length = sum(len((frag.get("content") or "")) for frag in fragments)

            row: dict[str, str] = {
                "id": str(resource.get("id", "")),
                "title": str(resource.get("title", "") or ""),
                "linked_parents": json.dumps(
                    resource.get("linked_parents", []),
                    ensure_ascii=False,
                ),
                "fragments_count": str(len(fragments)),
                "text_length": str(text_length),
            }

            flat_meta = _flatten_for_csv(metadata)
            row.update(flat_meta)
            dynamic_fields.update(flat_meta.keys())

            flattened_rows.append(row)

        fieldnames = [
            "id",
            "title",
            "linked_parents",
            "fragments_count",
            "text_length",
            *sorted(dynamic_fields),
        ]

        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in flattened_rows:
                writer.writerow(row)

    def _make_fetcher(self) -> Fetcher:
        """Create and return a Fetcher instance based on the configuration.
                This method checks the fetcher type specified in the configuration and initializes either a GoFetcher or
        an HttpxFetcher with the appropriate parameters. The GoFetcher is initialized with parameters specific to the Go implementation, while the HttpxFetcher is initialized with parameters suitable for Python HTTP requests. The method returns an instance of Fetcher that can be used for making requests to the DTS endpoint.

        :return: An instance of Fetcher (either GoFetcher or HttpxFetcher) initialized according to the configuration.
        :rtype: Fetcher
        """
        # default python/httpx
        return HttpxFetcher(
            endpoint=self.config.endpoint_dts,
            timeout=self.config.request_timeout,
            concurrency=self.config.concurrency,
            retries=self.config.retries,
            backoff_ms=self.config.backoff_ms,
            stats=self._stats,
        )

    def close(self):
        """Close any resources used by the ThunderDots client, such as thread pools or fetcher connections."""
        if self._executor:
            self._executor.shutdown(wait=False)
            self._executor = None

    async def _async_fetch(self) -> None:
        """Asynchronous implementation of the fetch operation, which performs the main fetching and processing pipeline."""
        loop = asyncio.get_running_loop()
        if self._executor is None:
            self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=32)
        loop.set_default_executor(self._executor)

        self._stats.start()
        ui = UI(enabled=self.config.verbose)

        fetcher: Fetcher = self._make_fetcher()

        try:
            async with ui:
                try:
                    ui.start_walk()

                    collections, resources = await walk_collections(
                        fetcher, self.config, self._stats, ui=ui
                    )

                    ui.start_resources(total=len(resources))

                    resource_results = await fetch_resources(
                        fetcher, self.config, resources, self._stats, ui=ui
                    )

                    self._results = build_output(
                        collections,
                        resource_results,
                        self._stats,
                        _package_version(),
                        collection_metadata_dublincore=self.config.collection_params.metadata_dublincore,
                        collection_metadata_extensions=self.config.collection_params.metadata_extensions,
                    )

                    if self.config.validate:
                        self._validate_results_if_needed()
                    self._write_results_if_needed()
                    self._write_cache_csv_if_needed()

                finally:
                    try:
                        await fetcher.aclose()
                    except Exception:
                        pass

        finally:
            self._stats.stop()
            ui.finalize(self._stats.to_dict())

    def notices(self) -> list[DotsNotice]:
        """Convert the resource results into a list of DotsNotice objects, which are ORM representations of the notices that can be used for further processing or output formatting."""
        return [
            DotsNotice.from_resource_result(item)
            for item in self.results().get("resource_results", [])
        ]

    def to_elastic_documents(self, *, include_fragments: bool = True) -> list[dict[str, Any]]:
        """Convert the resource results into a list of dictionaries formatted as ElasticSearch documents, with options to include fragments and raw metadata. Each notice is transformed into a format suitable for indexing in ElasticSearch, with fields such as "id", "title, "linked_parents", "metadata", and optionally "fragments" and "raw_metadata" based on the parameters provided.

        :param include_fragments: Whether to include the "fragments" field in the output documents (default: True).
        :type include_fragments: bool
        :return: A list of dictionaries, each representing an ElasticSearch document for a notice,
        with fields formatted according to the DotsNotice.to_elastic_document method and the specified parameters.
        :rtype: list[dict[str, Any]]
        """
        return [
            notice.to_elastic_document(
                include_fragments=include_fragments,
            )
            for notice in self.notices()
        ]

    def to_elastic_actions(
        self,
        *,
        include_fragments: bool = True,
        index: str,
    ) -> list[dict[str, Any]]:
        """Convert the resource results into a list of dictionaries formatted as ElasticSearch bulk API actions,
        with options to include fragments and raw metadata.
        Each notice is transformed into a format suitable for bulk
        indexing in ElasticSearch, with an action dictionary
        containing the index name and document ID,
        followed by the document itself formatted according
        to the DotsNotice.to_elastic_action method and
        the specified parameters.

        :param index: The name of the ElasticSearch index to use in the bulk actions.
        :type index: str
        :param include_fragments: Whether to include the "fragments" field in the output actions (default: True).
        :type include_fragments: bool
        :return: A list of dictionaries, each representing an ElasticSearch bulk API action for a
        :rtype: list[dict[str, Any]]
        """
        return [
            notice.to_elastic_action(
                index=index,
                include_fragments=include_fragments,
            )
            for notice in self.notices()
        ]

    def to_qdrant_payloads(
        self, *, include_fragments: bool = True, include_raw: bool = False
    ) -> list[dict[str, Any]]:
        """Convert the resource results into a list of dictionaries formatted as Qdrant payloads, with options to include fragments and raw metadata. Each notice is transformed into a format suitable for indexing in Qdrant, with fields such as "id", "title, "linked_parents", "metadata", and optionally "fragments" and "raw_metadata" based on the parameters provided.

        :param include_fragments: Whether to include the "fragments" field in the output payloads (default: True).
        :type include_fragments: bool
        :param include_raw: Whether to include the "raw_metadata" field in the output payload
                            (default: False).
        :type include_raw: bool
        :return: A list of dictionaries, each representing a Qdrant payload for a notice
        with fields formatted according to the DotsNotice.to_qdrant_payload method and the specified parameters.
        :rtype: list[dict[str, Any]]
        """
        return [
            notice.to_qdrant_payload(
                include_fragments=include_fragments,
                include_raw=include_raw,
            )
            for notice in self.notices()
        ]

    def to_records(
        self,
        *,
        column_map: dict[str, str] | None = None,
        include_text: bool = True,
        include_fragments: bool = False,
    ) -> list[dict[str, Any]]:
        """Return a list of flat dictionaries, one per resource notice, ready for tabular use.

        When *column_map* is ``None`` every column is included using its default name.
        When *column_map* is provided only the listed columns are included, renamed to
        their mapped values.  Keys follow the same naming scheme as
        :meth:`DotsNotice.to_row` (e.g. ``"dublincore.creator"``, ``"extensions.publisher"``).

        :param column_map: Optional mapping of ``{default_column_name: desired_name}``.
            If given, only columns present in the map are returned.
        :type column_map: dict[str, str] | None
        :param include_text: Include the ``text`` column.
        :type include_text: bool
        :param include_fragments: Include the ``fragments`` column.
        :type include_fragments: bool
        :return: List of flat row dictionaries.
        :rtype: list[dict[str, Any]]
        """
        rows = [
            notice.to_row(include_text=include_text, include_fragments=include_fragments)
            for notice in self.notices()
        ]

        if not column_map:
            return rows

        return [
            {column_map[key]: row[key] for key in column_map if key in row}
            for row in rows
        ]

    def to_dataframe(
        self,
        *,
        backend: str = "pandas",
        column_map: dict[str, str] | None = None,
        include_text: bool = True,
        include_fragments: bool = False,
    ) -> Any:
        """Return a Pandas or Polars DataFrame of the fetched resources.

        Columns follow the flat schema from :meth:`to_records`.  Use *column_map* to
        both select and rename columns in one step.

        Example::

            df = client.to_dataframe(
                backend="polars",
                column_map={
                    "id": "resource_id",
                    "dublincore.creator": "author",
                    "dublincore.date": "year",
                    "text": "full_text",
                },
            )

        :param backend: ``"pandas"`` or ``"polars"``.  The corresponding library must be
            installed; a clear :exc:`ImportError` is raised otherwise.
        :type backend: str
        :param column_map: Optional mapping of ``{default_column_name: desired_name}``.
            If given, only columns present in the map are returned.
        :type column_map: dict[str, str] | None
        :param include_text: Include the ``text`` column.
        :type include_text: bool
        :param include_fragments: Include the ``fragments`` column.
        :type include_fragments: bool
        :return: A DataFrame instance from the requested backend.
        :rtype: pandas.DataFrame | polars.DataFrame
        :raises ValueError: If *backend* is not ``"pandas"`` or ``"polars"``.
        :raises ImportError: If the requested backend library is not installed.
        """
        records = self.to_records(
            column_map=column_map,
            include_text=include_text,
            include_fragments=include_fragments,
        )

        if backend == "pandas":
            try:
                import pandas as pd
            except ImportError as exc:
                raise ImportError(
                    "pandas is required for backend='pandas'. "
                    "Install it with: uv install pandas or pip install pandas"
                ) from exc
            return pd.DataFrame(records)

        if backend == "polars":
            try:
                import polars as pl
            except ImportError as exc:
                raise ImportError(
                    "polars is required for backend='polars'. "
                    "Install it with: uv install polars or pip install polars"
                ) from exc
            return pl.from_dicts(records) if records else pl.DataFrame()

        raise ValueError(f"Unknown backend '{backend}'. Choose 'pandas' or 'polars'.")

    def to_qdrant_points(
        self,
        *,
        vectors: list[list[float] | dict[str, Any]] | None = None,
        include_fragments: bool = True,
        include_raw: bool = False,
    ) -> list[dict[str, Any]]:
        """Convert the resource results into a list of dictionaries formatted as Qdrant points, with options to include fragments, raw metadata, and associated vectors. Each notice is transformed into a format suitable for indexing in Qdrant, with fields such as "id", "title, "linked_parents", "metadata", and optionally "fragments" and raw_metadata" based on the parameters provided. If vectors are provided, they are included in the point data for each notice.

        :param vectors: An optional list of vectors to include in the point data for each notice. If provided, the length of this list must match the number of notices, and each vector will be included in the corresponding notice's point data (default: None).
        :type vectors: list[list[float] | dict[str, Any]] | None
        :param include_fragments: Whether to include the "fragments" field in the output
                            points (default: True).
        :type include_fragments: bool
        :param include_raw: Whether to include the "raw_metadata" field in the output points
                            (default: False).
        :type include_raw: bool
        :return: A list of dictionaries, each representing a Qdrant point for a notice
        with fields formatted according to the DotsNotice.to_qdrant_point method and the specified parameters, including vectors if provided.
        :rtype: list[dict[str, Any]]
        """
        notices = self.notices()

        if vectors is not None and len(vectors) != len(notices):
            raise ValueError(
                f"vectors length mismatch: got {len(vectors)} vectors for {len(notices)} notices"
            )

        return [
            notice.to_qdrant_point(
                vector=None if vectors is None else vectors[index],
                include_fragments=include_fragments,
                include_raw=include_raw,
            )
            for index, notice in enumerate(notices)
        ]
