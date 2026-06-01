# -*- coding: utf-8 -*-
"""config.py

Configuration dataclasses for ThunderDots, with helper methods to create instances from dicts and ensure list fields are properly handled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import warnings

from typing import Any


def _as_list(x: Any) -> list[str]:
    if x is None:
        return []

    if isinstance(x, str):
        return [x]

    if isinstance(x, list):
        return [str(v) for v in x]

    return [str(v) for v in list(x)]


def _optional_list(d: dict[str, Any], key: str) -> list[str] | None:
    if key not in d:
        return None
    return _as_list(d.get(key))


def _split_legacy_metadata_paths(paths: list[str]) -> tuple[list[str], list[str]]:
    dc: list[str] = []
    ext: list[str] = []

    for item in paths:
        item = str(item).strip()

        if item.startswith("dublincore."):
            dc.append(item.removeprefix("dublincore."))
        elif item.startswith("dublinCore."):
            dc.append(item.removeprefix("dublinCore."))
        elif item.startswith("extensions."):
            ext.append(item.removeprefix("extensions."))
        elif item.startswith("dct:"):
            ext.append(item)
        else:
            dc.append(item)

    return dc, ext


@dataclass(slots=True)
class CollectionParams:
    collection_id: str | None = None
    excluded_ids: list[str] = field(default_factory=list)
    metadata_dublincore: list[str] | None = None
    metadata_extensions: list[str] | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "CollectionParams":
        d = d or {}

        if d.get("keep_metadata"):
            warnings.warn(
                "'keep_metadata' is deprecated. Use 'metadata_dublincore' and "
                "'metadata_extensions' instead.",
                DeprecationWarning,
                stacklevel=2,
            )

        legacy_dc, legacy_ext = _split_legacy_metadata_paths(_as_list(d.get("keep_metadata")))

        metadata_dublincore = _optional_list(d, "metadata_dublincore")
        metadata_extensions = _optional_list(d, "metadata_extensions")

        return cls(
            collection_id=d.get("collection_id"),
            excluded_ids=_as_list(d.get("excluded_ids")),
            metadata_dublincore=(
                metadata_dublincore if metadata_dublincore is not None else legacy_dc or None
            ),
            metadata_extensions=(
                metadata_extensions if metadata_extensions is not None else legacy_ext or None
            ),
        )


@dataclass(slots=True)
class ResourceParams:
    metadata_dublincore: list[str] | None = None
    metadata_extensions: list[str] | None = None
    add_head_to_content: bool = True
    include_breadcrumb: bool = True
    exclude_heads_contains: list[str] = field(default_factory=list)
    fetch_document: bool = True
    fetch_navigation: bool = True
    fragment_mode: str = "auto"
    fragment_xpath: str | None = None
    title_xpath: str = "./tei:head"
    remove_fragment_heads: bool = True
    generated_id_prefix: str = "__DOCUMENT__"

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "ResourceParams":
        d = d or {}
        if d.get("keep_metadata"):
            warnings.warn(
                "'keep_metadata' is deprecated. Use 'metadata_dublincore' and "
                "'metadata_extensions' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        legacy_dc, legacy_ext = _split_legacy_metadata_paths(_as_list(d.get("keep_metadata")))
        metadata_dublincore = _optional_list(d, "metadata_dublincore")
        metadata_extensions = _optional_list(d, "metadata_extensions")
        return cls(
            metadata_dublincore=metadata_dublincore
            if metadata_dublincore is not None
            else legacy_dc or None,
            metadata_extensions=metadata_extensions
            if metadata_extensions is not None
            else legacy_ext or None,
            add_head_to_content=bool(d.get("add_head_to_content", True)),
            include_breadcrumb=bool(d.get("include_breadcrumb", True)),
            exclude_heads_contains=_as_list(d.get("exclude_heads_contains")),
            fetch_document=bool(d.get("fetch_document", True)),
            fetch_navigation=bool(d.get("fetch_navigation", True)),
            fragment_mode=str(d.get("fragment_mode", "auto")),
            fragment_xpath=d.get("fragment_xpath"),
            title_xpath=str(d.get("title_xpath", "./tei:head")),
            remove_fragment_heads=bool(d.get("remove_fragment_heads", True)),
            generated_id_prefix=str(d.get("generated_id_prefix", "__DOCUMENT__")),
        )


@dataclass(slots=True)
class ThunderDotsConfig:
    endpoint_dts: str
    fetch_collection_metadata: bool = True
    fetch_resource_metadata: bool = True
    validate: bool = False
    validation_profile: str = "dts"
    collection_params: CollectionParams = field(default_factory=CollectionParams)
    resource_params: ResourceParams = field(default_factory=ResourceParams)
    verbose: bool = True
    concurrency: int = 20
    timeout: float = 30.0
    request_timeout: float = 20.0
    retries: int = 2
    backoff_ms: int = 200
    output_path: str | None = None
    cache_csv_path: str | None = None
    use_cache: bool = True
