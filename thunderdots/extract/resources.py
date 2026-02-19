# -*- coding: utf-8 -*-

"""resources.py

Fetch and extract text from resources.
"""

from __future__ import annotations

import asyncio
from typing import Any

from .tei import extract_document_text_fast, extract_fragments
from ..normalize.metadata import keep_paths
from ..config import ThunderDotsConfig
from ..fetcher import Fetcher


async def fetch_resources(
    fetcher: Fetcher,
    config: ThunderDotsConfig,
    resources: list[tuple[dict[str, Any], list[str]]],
    stats,
    ui: Any = None,
) -> list[dict[str, Any]]:
    """Fetch and extract text from resources, with concurrency and progress tracking.

    :param fetcher: Fetcher instance to use for HTTP requests.
    :type fetcher: Fetcher
    :param config: ThunderDotsConfig with resource_params.keep_metadata.
    :type config: ThunderDotsConfig
    :param resources: List of tuples (resource_data, parent_ids) to process.
    :type resources: list[tuple[dict[str, Any], list[str]]]
    :param stats: Stats object to update with http_errors count.
    :type stats: Stats
    :param ui: Optional UI object to update progress.
    :type ui: Any, optional
    :return: List of processed resource dicts with id, title, linked_parents,
             metadata, and fragments.
    :rtype: list[dict[str, Any]]
    """
    workers_n = max(1, int(config.concurrency))
    total = len(resources)

    queue: asyncio.Queue = asyncio.Queue()
    for item in resources:
        queue.put_nowait(item)

    keep = list(config.resource_params.keep_metadata or [])

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
                try:
                    max_depth = int((data.get("citationTrees") or {}).get("maxCiteDepth") or 0)
                except Exception:
                    max_depth = 0

                if max_depth == 0:
                    doc = await fetcher.get_text("/document", params={"resource": rid})
                    fragments = await asyncio.to_thread(extract_document_text_fast, doc)
                else:
                    nav_task = fetcher.get_json("/navigation", params={"resource": rid, "down": -1})
                    doc_task = fetcher.get_text("/document", params={"resource": rid})
                    nav, doc = await asyncio.gather(nav_task, doc_task)
                    fragments = await asyncio.to_thread(extract_fragments, nav, doc)

                full_meta = {
                    "dublincore": data.get("dublincore", {}) or {},
                    "extensions": data.get("extensions", {}) or {},
                }
                filtered = keep_paths(full_meta, keep)
                filtered = {k: v for k, v in filtered.items() if v}

                item = {
                    "id": rid,
                    "title": data.get("title"),
                    "linked_parents": parents,
                    "metadata": filtered,
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
                        ui.update_resources(done=done, total=total, http_errors=stats.http_errors)
                queue.task_done()

    workers = [asyncio.create_task(worker()) for _ in range(workers_n)]
    await asyncio.gather(*workers)
    return out
