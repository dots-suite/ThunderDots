# -*- coding: utf-8 -*-

"""client.py

ThunderDots client interface (single Python pipeline, optional Go fetcher).
"""

from __future__ import annotations

import concurrent.futures
import asyncio
import json
from pathlib import Path
from typing import Any

from .ui import UI
from .stats import Stats
from .config import (ThunderDotsConfig,
                     CollectionParams,
                     ResourceParams)
from .fetcher import (HttpxFetcher,
                      GoFetcher,
                      Fetcher)
from .extract.walker import walk_collections
from .extract.resources import fetch_resources
from .normalize.output import build_output
from .__version__ import __version__

class ThunderDots:
    def __init__(
        self,
        endpoint_dts: str,
        fetch_collection_metadata: bool = True,
        fetch_resource_metadata: bool = True,
        collection_params: dict[str, Any] | None = None,
        resource_params: dict[str, Any] | None = None,
        verbose: bool = True,
        concurrency: int = 20,
        timeout: float = 30.0,
        fetcher: str = "python",
        go_lib_path: str | None = "native/build/libthunderdots.dylib",
        # Go tuning
        request_timeout: float = 20.0,
        total_timeout: float = 0.0,
        max_inflight: int | None = None,
        retries: int = 2,
        backoff_ms: int = 200,
        output_path: str | None = None,
        **_: Any,
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
        :param verbose: Whether to enable verbose logging and UI (default: True).
        :type verbose: bool
        :param concurrency: Number of concurrent fetches for Python fetcher (default: 20
        :type concurrency: int
        :param timeout: Request timeout in seconds for Python fetcher (default: 30.
        :type timeout: float
        :param fetcher: Fetcher backend to use, either "python" or "go" (default: "python").
        :type fetcher: str
        :param go_lib_path: Path to the Go fetcher shared library, required if fetch
                            is set to "go" (default: "native/build/libthunderdots.dylib").
        :type go_lib_path: str | None
        :param request_timeout: Request timeout in seconds for Go fetcher (default: 20
        :type request_timeout: float
        :param total_timeout: Total timeout in seconds for Go fetcher, 0 means no
                                limit (default: 0).
        :type total_timeout: float
        :param max_inflight: Max concurrent requests for Go fetcher (default: 100
                            if fetcher is "go", otherwise defaults to max(10, concurrency * 2)).
        :type max_inflight: int | None
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
        if max_inflight is None:
            max_inflight = max(10, concurrency * 2)

        endpoint = (endpoint_dts or "").rstrip("/")
        if not endpoint:
            raise ValueError("endpoint_dts is required")

        fetcher = (fetcher or "python").strip().lower()
        if fetcher not in ("python", "go"):
            raise ValueError('fetcher must be "python" or "go"')

        self.config = ThunderDotsConfig(
            endpoint_dts=endpoint,
            fetch_collection_metadata=fetch_collection_metadata,
            fetch_resource_metadata=fetch_resource_metadata,
            collection_params=CollectionParams.from_dict(collection_params),
            resource_params=ResourceParams.from_dict(resource_params),
            verbose=verbose,
            concurrency=int(concurrency),
            timeout=float(timeout),
            fetcher=fetcher,
            go_lib_path=go_lib_path,
            request_timeout=float(request_timeout),
            total_timeout=float(total_timeout),
            max_inflight=int(max_inflight),
            retries=int(retries),
            backoff_ms=int(backoff_ms),
            output_path=output_path,
        )

        self._stats = Stats()
        self._results: dict[str, Any] | None = None
        self._executor: concurrent.futures.ThreadPoolExecutor | None = None

    # ---------------- PUBLIC API ---------------- #

    def fetch(self) -> None:
        """Fetch collections and resources from the DTS endpoint and build results.

        This method runs the main fetching and processing pipeline, which includes:
        - Walking collections starting from the specified collection_id, applying exclusions and metadata fetching as configured.
        - Fetching resources linked from the collections, applying metadata fetching and filtering as configured.
        - Building the final results dictionary with collection and resource results, along with stats and version info
        - Optionally saving the results to a JSON file if output_path is configured.
        """
        asyncio.run(self._async_fetch())

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

    def _make_fetcher(self) -> Fetcher:
        """Create and return a Fetcher instance based on the configuration.
        This method checks the fetcher type specified in the configuration and initializes either a GoFetcher or
an HttpxFetcher with the appropriate parameters. The GoFetcher is initialized with parameters specific to the Go implementation, while the HttpxFetcher is initialized with parameters suitable for Python HTTP requests. The method returns an instance of Fetcher that can be used for making requests to the DTS endpoint.

:return: An instance of Fetcher (either GoFetcher or HttpxFetcher) initialized according to the configuration.
:rtype: Fetcher
        """
        if self.config.fetcher == "go":
            return GoFetcher(
                lib_path=self.config.go_lib_path,
                endpoint=self.config.endpoint_dts,
                request_timeout=self.config.request_timeout,
                total_timeout=self.config.total_timeout,
                max_inflight=self.config.max_inflight,
                retries=self.config.retries,
                backoff_ms=self.config.backoff_ms,
            )
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
                    __version__,
                    keep_collection_meta=self.config.collection_params.keep_metadata,
                )
                self._write_results_if_needed()

            finally:
                try:
                    await fetcher.aclose()
                except Exception:
                    pass

                self._stats.stop()
                ui.finalize(self._stats.to_dict())
