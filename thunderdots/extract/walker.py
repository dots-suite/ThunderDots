#-*- coding: utf-8 -*-

"""walker.py

Iterate over a collection and its sub-collections, fetching their data and the data of their resources.
Using traversal (BFS) with a queue and a set of seen IDs to avoid cycles/dedupes.
"""
from __future__ import annotations

from typing import Tuple, List, Optional
import asyncio

async def _fetch_collection(fetcher, cid, stats, ui=None):
    params = {"id": cid} if cid else {}
    try:
        data = await fetcher.get_json("/collection", params=params)
        if data is None:
            raise RuntimeError("non-200")
        return data
    except Exception as e:
        stats.http_errors += 1
        if ui:
            ui.debug(f"[ThunderDots] skip collection {cid} → {e}")
        return None


async def walk_collections(fetcher, config, stats, ui=None) -> Tuple[List[dict], List[dict]]:
    concurrency = max(1, int(config.concurrency))

    collections: list[tuple[dict, list[str]]] = []
    resources: list[tuple[dict, list[str]]] = []

    # Queue d'items à traiter : (cid, parents)
    q: asyncio.Queue[Optional[tuple[str, list[str]]]] = asyncio.Queue()
    await q.put((config.collection_params.collection_id or "", []))

    excluded = set(config.collection_params.excluded_ids or [])

    # seen protège des cycles/doublons
    seen: set[str] = set()
    seen_lock = asyncio.Lock()

    walked = 0
    out_lock = asyncio.Lock()
    walked_lock = asyncio.Lock()

    SENTINEL: Optional[tuple[str, list[str]]] = None


    async def worker() -> None:
        nonlocal walked
        while True:
            item = await q.get()
            try:
                if item is SENTINEL:
                    return

                cid, parents = item
                data = await _fetch_collection(fetcher, cid, stats, ui=ui)
                if data is None:
                    continue  # important: ne pas tuer le worker

                async with walked_lock:
                    walked += 1
                    cur_walked = walked

                typ = data.get("@type")
                if typ == "Resource":
                    async with out_lock:
                        resources.append((data, parents))
                else:
                    async with out_lock:
                        collections.append((data, parents))

                    parent_id = data.get("@id")
                    for m in (data.get("member") or []):
                        mid = (m or {}).get("@id")
                        if not mid or mid in excluded:
                            continue

                        async with seen_lock:
                            if mid in seen:
                                continue
                            seen.add(mid)

                        await q.put((mid, parents + [parent_id]))

                if ui:
                    ui.update_collections(
                        walked=cur_walked,
                        collections=len(collections),
                        resources=len(resources),
                        http_errors=stats.http_errors,
                    )
            finally:
                q.task_done()

    workers = [asyncio.create_task(worker()) for _ in range(concurrency)]

    # Attend que tout ce qui a été enqueued soit traité (y compris ce qui est ajouté en cours de route)
    await q.join()

    # Stop proprement les workers (sinon ils restent bloqués sur q.get())
    for _ in range(concurrency):
        await q.put(SENTINEL)
    await asyncio.gather(*workers)

    if ui:
        ui.finish_walk()

    return collections, resources