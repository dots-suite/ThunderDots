# -*- coding: utf-8 -*-

"""resources.py

Fetch and extract text from resources.
"""

from __future__ import annotations

import asyncio
from typing import Any

from .tei import (
    extract_document_text_fast,
    extract_fragments,
    extract_fragments_by_xpath,
)
from ..config import ThunderDotsConfig
from ..fetcher import Fetcher
from ..normalize.dates import enrich_temporal_metadata
from ..normalize.metadata import build_metadata


async def _fetch_document(fetcher: Any, resource_id: str) -> bytes | str:
    """Fetch the TEI document of a resource, as bytes when the fetcher supports it.

    Bytes go straight to lxml, which avoids decoding the body to ``str`` and re-encoding
    it for the parser. Fetchers without ``get_bytes`` (custom implementations) fall back
    to ``get_text``.

    :param fetcher: Fetcher instance.
    :type fetcher: Any
    :param resource_id: DTS resource identifier.
    :type resource_id: str
    :return: The document body.
    :rtype: bytes | str
    """
    params = {"resource": resource_id}
    get_bytes = getattr(fetcher, "get_bytes", None)
    if callable(get_bytes):
        return await get_bytes("/document", params=params)
    return await fetcher.get_text("/document", params=params)


def attach_fragment_temporal_index(fragments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add a ``temporal`` index to each fragment, derived from its own metadata only.

    The index is computed with :func:`enrich_temporal_metadata` on ``fragment["metadata"]``
    (Dublin Core, extensions and TEI dates). A fragment without explicit temporal metadata
    gets an empty dictionary: resource-level dates are never inherited, because they do
    not necessarily apply to a given fragment.

    :param fragments: Fragments produced by the TEI extractors (modified in place).
    :type fragments: list[dict[str, Any]]
    :return: The same list, for convenience.
    :rtype: list[dict[str, Any]]
    """
    for fragment in fragments:
        metadata = fragment.get("metadata")
        fragment["temporal"] = (
            enrich_temporal_metadata(metadata) if isinstance(metadata, dict) else {}
        )
    return fragments


async def fetch_resources(
    fetcher: Fetcher,
    config: ThunderDotsConfig,
    resources: list[tuple[dict[str, Any], list[str]]],
    stats,
    ui: Any = None,
) -> list[dict[str, Any]]:
    """Fetch and extract text from resources, with concurrency and progress tracking.

    :param fetcher: Fetcher instance to use for HTTP requests
    :type fetcher: Fetcher
    :param config: ThunderDotsConfig instance with configuration parameters
    :type config: ThunderDotsConfig
    :param resources: List of tuples (resource_data, parent_ids) to process
    :type resources: list[tuple[dict[str, Any], list[str]]]
    :param stats: Stats object to track HTTP errors
    :type stats: Any
    :param ui: Optional UI object for progress updates
    :type ui: Any, optional
    :return: List of processed resources with extracted fragments
    :rtype: list[dict[str, Any]]
    """

    workers_n = max(1, int(config.concurrency))
    total = len(resources)

    include_breadcrumb = bool(config.resource_params.include_breadcrumb)
    add_head_to_content = bool(config.resource_params.add_head_to_content)
    exclude_heads_contains = list(config.resource_params.exclude_heads_contains or [])

    fragment_dublincore_metadata_params = config.fragment_params.metadata_dublincore
    fragment_extensions_metadata_params = config.fragment_params.metadata_extensions
    fragment_temporal_xpath = config.fragment_params.temporal_xpath
    fragment_temporal_index = bool(config.fragment_params.temporal_index_enabled)

    fetch_document = bool(config.resource_params.fetch_document)
    fetch_navigation = bool(config.resource_params.fetch_navigation)

    fragment_mode = str(config.resource_params.fragment_mode or "auto")
    fragment_xpath = config.resource_params.fragment_xpath
    title_xpath = config.resource_params.title_xpath
    remove_fragment_heads = bool(config.resource_params.remove_fragment_heads)
    generated_id_prefix = config.resource_params.generated_id_prefix

    queue: asyncio.Queue = asyncio.Queue()

    for item in resources:
        queue.put_nowait(item)

    out: list[dict[str, Any]] = []
    out_lock = asyncio.Lock()

    done = 0
    last_ui = 0.0
    ui_period = 0.2

    async def worker():
        nonlocal done, last_ui

        while True:
            try:
                data, parents = queue.get_nowait()
            except asyncio.QueueEmpty:
                return

            rid = data.get("@id") or ""

            if not rid:
                queue.task_done()
                continue

            try:
                metadata = build_metadata(
                    data,
                    metadata_dublincore=config.resource_params.metadata_dublincore,
                    metadata_extensions=config.resource_params.metadata_extensions,
                )
                metadata = {k: v for k, v in metadata.items() if v}

                fragments: list[dict[str, Any]] = []

                if fetch_document:
                    try:
                        max_depth = int((data.get("citationTrees") or {}).get("maxCiteDepth") or 0)
                    except Exception:
                        max_depth = 0

                    # ------------------------------------------------------------
                    # 1. Navigation mode :
                    #    We use the /navigation endpoint to get the structure of the resource and its fragments
                    #    And then we extract the text of each fragment with /document
                    # ------------------------------------------------------------
                    if fragment_mode == "navigation" or (
                        fragment_mode == "auto" and fetch_navigation and max_depth > 0
                    ):
                        nav_task = fetcher.get_json(
                            "/navigation",
                            params={"resource": rid, "down": -1},
                        )
                        doc_task = _fetch_document(fetcher, rid)

                        nav, doc = await asyncio.gather(nav_task, doc_task)

                        fragments = await asyncio.to_thread(
                            extract_fragments,
                            nav,
                            doc,
                            add_head_to_content=add_head_to_content,
                            exclude_heads_contains=exclude_heads_contains,
                            include_breadcrumb=include_breadcrumb,
                            fragment_metadata_dublincore_params=fragment_dublincore_metadata_params,
                            fragment_metadata_extensions_params=fragment_extensions_metadata_params,
                            temporal_xpath=fragment_temporal_xpath,
                        )

                    # ------------------------------------------------------------
                    # 2. TEI XPath mode :
                    #    We ingore the /navigation endpoint
                    #    and we split the TEI XML with fragment_xpath
                    # ------------------------------------------------------------
                    elif fragment_mode == "tei_xpath":
                        if not fragment_xpath:
                            raise ValueError(
                                "resource_params.fragment_xpath is required "
                                "when fragment_mode='tei_xpath'"
                            )

                        doc = await _fetch_document(fetcher, rid)

                        fragments = await asyncio.to_thread(
                            extract_fragments_by_xpath,
                            doc,
                            fragment_xpath=fragment_xpath,
                            resource_id=rid,
                            title_xpath=title_xpath,
                            remove_fragment_heads=remove_fragment_heads,
                            add_head_to_content=add_head_to_content,
                            exclude_heads_contains=exclude_heads_contains,
                            include_breadcrumb=include_breadcrumb,
                            generated_id_prefix=generated_id_prefix,
                            temporal_xpath=fragment_temporal_xpath,
                        )

                    # ------------------------------------------------------------
                    # 3. Document mode :
                    #    One unique fragment containing the whole text of the resource,
                    #    extracted from /document endpoint
                    # ------------------------------------------------------------
                    elif fragment_mode == "document" or fragment_mode == "auto":
                        doc = await _fetch_document(fetcher, rid)

                        fragments = await asyncio.to_thread(
                            extract_document_text_fast,
                            doc,
                            add_head_to_content=add_head_to_content,
                            exclude_heads_contains=exclude_heads_contains,
                            include_breadcrumb=include_breadcrumb,
                            temporal_xpath=fragment_temporal_xpath,
                        )

                    else:
                        raise ValueError(f"Unknown fragment_mode: {fragment_mode}")

                    if fragment_temporal_index:
                        attach_fragment_temporal_index(fragments)

                item = {
                    "id": rid,
                    "@type": data.get("@type") or "Resource",
                    "title": data.get("title"),
                    "linked_parents": parents,
                    "metadata": metadata,
                    "fragments": fragments,
                }

                async with out_lock:
                    out.append(item)

            except Exception as e:
                stats.http_errors += 1

                if ui:
                    ui.debug(f"[ThunderDots] skip resource {rid} → {e}")

            finally:
                done += 1
                if ui:
                    now = asyncio.get_running_loop().time()
                    if (now - last_ui) >= ui_period or done == total:
                        last_ui = now
                        ui.update_resources(
                            done=done,
                            total=total,
                            http_errors=stats.http_errors,
                        )
                queue.task_done()

    workers = [asyncio.create_task(worker()) for _ in range(workers_n)]

    await asyncio.gather(*workers)

    return out
