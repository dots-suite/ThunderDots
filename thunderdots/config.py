# -*- coding: utf-8 -*-
"""config.py

Configuration dataclasses for ThunderDots, with helper methods to create instances from dicts and ensure list fields are properly handled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _as_list(x: Any) -> list:
    """Helper to ensure a value is a list, or an empty list if None.

    :param x: The input value, which can be None, a list, or any iterable.
    :type x: Any
    :return: A list containing the elements of x if x is a list or iterable,
            or an empty list if x is None.
    :rtype: list
    """
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return list(x)


@dataclass(slots=True)
class CollectionParams:
    """Parameters for collection fetching and filtering."""

    collection_id: str | None = None
    excluded_ids: list[str] = field(default_factory=list)
    keep_metadata: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "CollectionParams":
        """Create a CollectionParams instance from a dictionary, ensuring list fields are lists.

        :param d: Dictionary containing collection parameters, with optional keys "collection_id", "excluded_ids", and "keep_metadata".
        :type d: dict[str, Any] | None
        :return: A CollectionParams instance with fields set according to the dictionary, ensuring excluded_ids
                    and keep_metadata are lists of strings.
        :rtype: CollectionParams
        """
        d = d or {}
        return cls(
            collection_id=d.get("collection_id"),
            excluded_ids=_as_list(d.get("excluded_ids")),
            keep_metadata=_as_list(d.get("keep_metadata")),
        )


@dataclass(slots=True)
class ResourceParams:
    """Parameters for resource fetching and filtering."""

    keep_metadata: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "ResourceParams":
        """Create a ResourceParams instance from a dictionary, ensuring keep_metadata is a list.

        :param d: Dictionary containing resource parameters, with an optional "keep_metadata" key.
        :type d: dict[str, Any] | None
        :return: A ResourceParams instance with keep_metadata set to a list of strings.
        :rtype: ResourceParams
        """
        d = d or {}
        return cls(keep_metadata=_as_list(d.get("keep_metadata")))


@dataclass(slots=True)
class ThunderDotsConfig:
    """Configuration for ThunderDots fetching and processing."""

    endpoint_dts: str  # required, e.g. "https://example.com/dts"
    fetch_collection_metadata: bool = (
        True  # whether to fetch metadata for collections (can be skipped if only ids are needed)
    )
    fetch_resource_metadata: bool = (
        True  # whether to fetch metadata for resources (can be skipped if only ids are needed)
    )
    collection_params: CollectionParams = field(
        default_factory=CollectionParams
    )  # parameters for collection fetching/filtering
    resource_params: ResourceParams = field(
        default_factory=ResourceParams
    )  # parameters for resource fetching/filtering
    verbose: bool = True

    concurrency: int = 20  # number of concurrent fetches for HttpxFetcher (Go fetcher has its own max_inflight param)
    timeout: float = 30.0  # for HttpxFetcher only, seconds per request (Go fetcher has its own request_timeout and total_timeout)

    # fetch backend (NOT "engine"): "python" | "go"
    fetcher: str = "python"  # default to python/httpx, can be set to "go" to use the Go fetcher (requires go_lib_path)
    go_lib_path: str | None = (
        None  # path to the Go fetcher shared library (e.g. "native/build/libthunderdots.dylib"), required if fetcher is "go"
    )

    # Go fetch tuning (also used as defaults in python where relevant)
    request_timeout: float = 20.0  # seconds, per request
    total_timeout: float = 0.0  # seconds, 0 = no limit (per call for Go)
    max_inflight: int = 100  # max concurrent requests for Go fetcher (also used as concurrency for python/httpx if fetcher is "python")
    retries: int = 2  # number of retries for failed requests (both fetchers)
    backoff_ms: int = 200  # base backoff in milliseconds for retries (both fetchers)

    # if user wants to save raw outputs (collections/resources) for debugging
    output_path: str | None = (
        None  # path to save the final output JSON (e.g. "output/results.json"), optional
    )
