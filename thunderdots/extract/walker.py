# -*- coding: utf-8 -*-

"""walker.py
Walk DTS collections and discover their resources using
Breadth-First Search (BFS) traversal. For each collection or resource,
resolve its direct parent collections using the Linked Parents API.

The ``member`` entries of a collection often carry enough information to avoid
requests: a complete Resource description (no need to request
``/collection?id=<member>``) and a ``totalParents`` count (no need to request
``/collection?id=<member>&nav=parents`` when the traversal already knows the
single parent). Both shortcuts are controlled by ``CollectionParams``.
"""

from __future__ import annotations

import asyncio
from typing import Any

from .parents import LinkedParentsResolver
from ..normalize.metadata import get_path


CollectionEntry = tuple[dict[str, Any], list[str]]
ResourceEntry = tuple[dict[str, Any], list[str]]

# Queue items contain:
#     (object identifier, direct parent discovered during traversal, member entry or None)
QueueItem = tuple[str, list[str], dict[str, Any] | None]

_DESCRIPTIVE_KEYS = ("dublincore", "dublinCore", "extensions")


def _member_block(member: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    """Return the first dictionary found under one of *keys* in a member entry."""
    for key in keys:
        value = member.get(key)
        if isinstance(value, dict):
            return value
    return {}


def member_describes_resource(
    member: dict[str, Any] | None,
    *,
    mode: bool | str,
    resource_params: Any,
) -> bool:
    """Decide whether a Resource ``member`` entry can stand in for its full description.

    :param member: Member entry found in a parent collection.
    :type member: dict[str, Any] | None
    :param mode: ``CollectionParams.trust_member_metadata``: ``True``, ``False`` or ``"auto"``.
        In ``"auto"`` mode the entry must be a Resource carrying ``citationTrees`` or
        ``document``, at least one metadata block, and every metadata key explicitly
        requested by *resource_params*.
    :type mode: bool | str
    :param resource_params: ``ResourceParams`` with the requested metadata filters.
    :type resource_params: Any
    :return: True when the member entry can be used without fetching the resource.
    :rtype: bool
    """
    if mode is False or not isinstance(member, dict):
        return False

    if member.get("@type") != "Resource":
        return False

    if mode is True:
        return True

    if "citationTrees" not in member and "document" not in member:
        return False

    if not any(isinstance(member.get(key), dict) for key in _DESCRIPTIVE_KEYS):
        return False

    requested = (
        (resource_params.metadata_dublincore, ("dublincore", "dublinCore")),
        (resource_params.metadata_extensions, ("extensions",)),
    )
    for wanted, keys in requested:
        if not wanted:
            continue
        block = _member_block(member, keys)
        if any(get_path(block, path) is None for path in wanted):
            return False

    return True


def member_gives_single_parent(
    member: dict[str, Any] | None,
    traversal_parents: list[str],
) -> bool:
    """Return True when ``totalParents`` confirms that the traversal parent is the only one.

    :param member: Member entry found in a parent collection.
    :type member: dict[str, Any] | None
    :param traversal_parents: Direct parent discovered during traversal.
    :type traversal_parents: list[str]
    :return: True when the ``nav=parents`` request can be skipped.
    :rtype: bool
    """
    if not isinstance(member, dict):
        return False

    total = member.get("totalParents")
    if isinstance(total, bool) or not isinstance(total, int):
        return False

    return total == 1 and len(traversal_parents) == 1


def _bump_skipped(stats: Any, n: int = 1) -> None:
    """Increment ``stats.requests_skipped`` when the stats object supports it."""
    if hasattr(stats, "requests_skipped"):
        stats.requests_skipped += n


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

    collection_params = config.collection_params
    resource_params = config.resource_params
    trust_member = collection_params.trust_member_metadata
    trust_parents = bool(collection_params.trust_total_parents)

    collections: list[CollectionEntry] = []
    resources: list[ResourceEntry] = []

    queue: asyncio.Queue[QueueItem | None] = asyncio.Queue()

    await queue.put(
        (
            collection_params.collection_id or "",
            [],
            None,
        )
    )

    excluded = set(collection_params.excluded_ids or [])

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

    def wants_parents(object_type: str | None) -> bool:
        """Return the linked-parents flag for a DTS type (both flags when unknown)."""
        if object_type == "Resource":
            return bool(resource_params.fetch_linked_parents)
        if object_type == "Collection":
            return bool(collection_params.fetch_linked_parents)
        return bool(resource_params.fetch_linked_parents or collection_params.fetch_linked_parents)

    async def worker() -> None:
        nonlocal walked

        while True:
            queue_item = await queue.get()

            try:
                if queue_item is sentinel:
                    return

                object_id, traversal_parents, member = queue_item
                hint_type = member.get("@type") if isinstance(member, dict) else None

                use_member = member_describes_resource(
                    member,
                    mode=trust_member,
                    resource_params=resource_params,
                )
                need_parents = wants_parents(hint_type)
                parents_from_hint = (
                    need_parents
                    and trust_parents
                    and member_gives_single_parent(member, traversal_parents)
                )

                data_coro = (
                    None if use_member else _fetch_collection(fetcher, object_id, stats, ui=ui)
                )
                parents_coro = (
                    parents_resolver.resolve(object_id, fallback=traversal_parents)
                    if need_parents and not parents_from_hint
                    else None
                )

                linked_parents_prefetch: list[str] = list(traversal_parents)

                if data_coro is not None and parents_coro is not None:
                    data, linked_parents_prefetch = await asyncio.gather(data_coro, parents_coro)
                elif data_coro is not None:
                    data = await data_coro
                else:
                    data = dict(member)
                    _bump_skipped(stats)
                    if parents_coro is not None:
                        linked_parents_prefetch = await parents_coro

                if parents_from_hint:
                    _bump_skipped(stats)

                if data is None:
                    continue

                current_id = str(data.get("@id") or object_id or "").strip()
                object_type = str(data.get("@type") or "Collection")
                fetch_parents = wants_parents(object_type)

                if not fetch_parents or parents_from_hint:
                    linked_parents = list(traversal_parents)
                elif parents_coro is None or (current_id and current_id != object_id):
                    # Parents were not prefetched (type unknown from the hint), or the
                    # server answered with another identifier: resolve now (cached).
                    linked_parents = await parents_resolver.resolve(
                        current_id or object_id,
                        fallback=traversal_parents,
                    )
                else:
                    linked_parents = linked_parents_prefetch

                async with walked_lock:
                    walked += 1
                    current_walked = walked

                if object_type == "Resource":
                    async with output_lock:
                        resources.append((data, linked_parents))

                else:
                    async with output_lock:
                        collections.append((data, linked_parents))

                    for child in data.get("member") or []:
                        if not isinstance(child, dict):
                            continue

                        child_id = child.get("@id")

                        if not isinstance(child_id, str):
                            continue

                        child_id = child_id.strip()

                        if not child_id or child_id in excluded:
                            continue

                        async with seen_lock:
                            if child_id in seen:
                                continue

                            seen.add(child_id)

                        # The traversal fallback represents a direct parent,
                        # not the complete ancestor chain.
                        direct_fallback = [current_id] if current_id else []

                        await queue.put(
                            (
                                child_id,
                                direct_fallback,
                                child,
                            )
                        )

                if ui:
                    # Root object + every identifier queued so far: the known upper bound
                    # of the walk, which grows as collections are discovered.
                    ui.update_collections(
                        walked=current_walked,
                        collections=len(collections),
                        resources=len(resources),
                        http_errors=stats.http_errors,
                        discovered=len(seen) + 1,
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
