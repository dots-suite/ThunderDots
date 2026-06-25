# -*- coding: utf-8 -*-

"""walker.py
Walk DTS collections and discover their resources using
Breadth-First Search (BFS) traversal. For each collection or resource,
resolve its direct parent collections using the Linked Parents API.
"""

from __future__ import annotations

import asyncio
from typing import Any

from .parents import LinkedParentsResolver


CollectionEntry = tuple[dict[str, Any], list[str]]
ResourceEntry = tuple[dict[str, Any], list[str]]


async def _fetch_collection(
    fetcher: Any,
    collection_id: str,
    stats: Any,
    ui: Any = None,
) -> dict[str, Any] | None:
    """Fetch one DTS collection or resource description.

    :param fetcher: An object with a ``get_json`` method for fetching DTS JSON.
    :type fetcher: Any
    :param collection_id: The DTS collection or resource identifier.
    :type collection_id: str
    :param stats: An object with an ``http_errors`` attribute for tracking errors.
    :type stats: Any
    :param ui: An optional UI object for logging debug messages.
    :type ui: Any, optional
    :return: The DTS collection or resource description as a dictionary, or ``None`` on
                failure.
    :rtype: dict[str, Any] | None
    """

    params = {"id": collection_id} if collection_id else {}

    try:
        data = await fetcher.get_json("/collection", params=params)

        if data is None:
            raise RuntimeError("empty or non-successful DTS response")

        return data

    except Exception as exc:
        # HttpxFetcher already records HTTP failures. This increment remains
        # useful for custom fetchers that raise without managing Stats.
        if fetcher.__class__.__name__ != "HttpxFetcher":
            stats.http_errors += 1

        if ui:
            ui.debug(f"[ThunderDots] skip collection {collection_id or '<root>'} → {exc}")

        return None


async def walk_collections(
    fetcher: Any,
    config: Any,
    stats: Any,
    ui: Any = None,
) -> tuple[list[CollectionEntry], list[ResourceEntry]]:
    """Walk collections and resolve direct parents for every DTS object.

    :param fetcher: An object with a ``get_json`` method for fetching DTS JSON.
    :type fetcher: Any
    :param config: A configuration object with collection and resource parameters.
    :type config: Any
    :param stats: An object with an ``http_errors`` attribute for tracking errors.
    :type stats: Any
    :param ui: An optional UI object for logging debug messages.
    :type ui: Any, optional
    :return: A tuple containing two lists: one for collections and one for resources.
    :rtype: tuple[list[CollectionEntry], list[ResourceEntry]]
    """

    concurrency = max(1, int(config.concurrency))

    collections: list[CollectionEntry] = []
    resources: list[ResourceEntry] = []

    # Queue items contain:
    #     (object identifier, direct parent discovered during traversal)
    queue: asyncio.Queue[tuple[str, list[str]] | None] = asyncio.Queue()

    await queue.put(
        (
            config.collection_params.collection_id or "",
            [],
        )
    )

    excluded = set(config.collection_params.excluded_ids or [])

    seen: set[str] = set()
    seen_lock = asyncio.Lock()

    output_lock = asyncio.Lock()
    walked_lock = asyncio.Lock()

    walked = 0

    parents_resolver = LinkedParentsResolver(
        fetcher,
        ui=ui,
    )

    sentinel = None

    async def worker() -> None:
        nonlocal walked

        while True:
            queue_item = await queue.get()

            try:
                if queue_item is sentinel:
                    return

                object_id, traversal_parents = queue_item

                need_parents = (
                    config.resource_params.fetch_linked_parents
                    or config.collection_params.fetch_linked_parents
                )

                if need_parents:
                    data, linked_parents_prefetch = await asyncio.gather(
                        _fetch_collection(fetcher, object_id, stats, ui=ui),
                        parents_resolver.resolve(object_id, fallback=traversal_parents),
                    )
                else:
                    data = await _fetch_collection(fetcher, object_id, stats, ui=ui)
                    linked_parents_prefetch = list(traversal_parents)

                if data is None:
                    continue

                current_id = str(data.get("@id") or object_id or "").strip()
                object_type = str(data.get("@type") or "Collection")

                if object_type == "Resource":
                    fetch_parents = bool(config.resource_params.fetch_linked_parents)
                else:
                    fetch_parents = bool(config.collection_params.fetch_linked_parents)

                if fetch_parents:
                    if current_id and current_id != object_id:
                        linked_parents = await parents_resolver.resolve(
                            current_id,
                            fallback=traversal_parents,
                        )
                    else:
                        linked_parents = linked_parents_prefetch
                else:
                    linked_parents = list(traversal_parents)

                async with walked_lock:
                    walked += 1
                    current_walked = walked

                if object_type == "Resource":
                    async with output_lock:
                        resources.append((data, linked_parents))

                else:
                    async with output_lock:
                        collections.append((data, linked_parents))

                    for member in data.get("member") or []:
                        if not isinstance(member, dict):
                            continue

                        member_id = member.get("@id")

                        if not isinstance(member_id, str):
                            continue

                        member_id = member_id.strip()

                        if not member_id or member_id in excluded:
                            continue

                        async with seen_lock:
                            if member_id in seen:
                                continue

                            seen.add(member_id)

                        # The traversal fallback represents a direct parent,
                        # not the complete ancestor chain.
                        direct_fallback = [current_id] if current_id else []

                        await queue.put(
                            (
                                member_id,
                                direct_fallback,
                            )
                        )

                if ui:
                    ui.update_collections(
                        walked=current_walked,
                        collections=len(collections),
                        resources=len(resources),
                        http_errors=stats.http_errors,
                    )

            finally:
                queue.task_done()

    workers = [asyncio.create_task(worker()) for _ in range(concurrency)]

    await queue.join()

    for _ in range(concurrency):
        await queue.put(sentinel)

    await asyncio.gather(*workers)

    if ui:
        ui.finish_walk()

    return collections, resources
