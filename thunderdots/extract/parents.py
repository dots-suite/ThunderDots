# -*- coding: utf-8 -*-

"""parents.py

Utilities for resolving DTS parent collections.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ..fetcher import Fetcher


def normalize_parent_ids(values: Any) -> list[str]:
    """Normalize, deduplicate and preserve the order of parent identifiers.

    :param values: A string, list, tuple or set of parent identifiers.
    :type values: str | list[str]
    :return: A list of unique, non-empty parent identifiers.
    :rtype: list[str]
    """

    if values is None:
        return []

    if isinstance(values, str):
        values = [values]

    if not isinstance(values, (list, tuple, set)):
        return []

    normalized: list[str] = []
    seen: set[str] = set()

    for value in values:
        if not isinstance(value, str):
            continue

        parent_id = value.strip()
        if not parent_id or parent_id in seen:
            continue

        seen.add(parent_id)
        normalized.append(parent_id)

    return normalized


def extract_linked_parent_ids(payload: Any) -> list[str]:
    """Extract parent identifiers from a DTS ``nav=parents`` response.

    Expected response shape::

        {
            "member": [
                {"@id": "ENCPOS"},
                {"@id": "OTHER_COLLECTION"}
            ]
        }

    :param payload: The JSON payload from a DTS collection request.
    :type payload: dict
    :return: A list of unique parent identifiers.
    :rtype: list[str]
    """

    if not isinstance(payload, dict):
        return []

    members = payload.get("member")
    if not isinstance(members, list):
        return []

    parent_ids: list[str] = []

    for member in members:
        if not isinstance(member, dict):
            continue

        parent_id = member.get("@id") or member.get("id")

        if isinstance(parent_id, str):
            parent_ids.append(parent_id)

    return normalize_parent_ids(parent_ids)


class LinkedParentsResolver:
    """Resolve DTS parents with a shared asynchronous cache.

    The resolver ensures that the same identifier is not requested several
    times concurrently. Failed or malformed responses fall back to the parent
    identifiers discovered during collection traversal.
    interface for logging debug messages.
    """

    def __init__(
        self,
        fetcher: Fetcher,
        *,
        ui: Any = None,
    ) -> None:
        self.fetcher = fetcher
        self.ui = ui

        self._cache: dict[str, list[str]] = {}
        self._inflight: dict[str, asyncio.Task[list[str] | None]] = {}
        self._lock = asyncio.Lock()

    async def _fetch(self, object_id: str) -> list[str] | None:
        """Fetch the parents of one DTS object.

        ``None`` means that the request failed or returned an invalid payload.
        An empty list means that the request succeeded and no parent exists.

        :param object_id: The DTS collection or resource identifier.
        :type object_id: str
        :return: A list of parent identifiers or ``None`` on failure.
        :rtype: list[str] | None
        """

        try:
            payload = await self.fetcher.get_json(
                "/collection",
                params={
                    "id": object_id,
                    "nav": "parents",
                },
            )
        except Exception as exc:
            if self.ui:
                self.ui.debug(f"[ThunderDots] unable to fetch parents for {object_id} → {exc}")
            return None

        if not isinstance(payload, dict):
            if self.ui:
                self.ui.debug(f"[ThunderDots] invalid parents response for {object_id}")
            return None

        return extract_linked_parent_ids(payload)

    async def resolve(
        self,
        object_id: str | None,
        *,
        fallback: list[str] | None = None,
    ) -> list[str]:
        """Return the direct parents of a collection or resource.

        :param object_id: The DTS collection or resource identifier.
        :type object_id: str | None
        :param fallback: A list of parent identifiers to use if the fetch fails.
        :type fallback: list[str] | None
        :return: A list of parent identifiers.
        :rtype: list[str]
        """

        normalized_id = str(object_id or "").strip()
        normalized_fallback = normalize_parent_ids(fallback)

        if not normalized_id:
            return normalized_fallback

        async with self._lock:
            cached = self._cache.get(normalized_id)
            if cached is not None:
                return list(cached)

            task = self._inflight.get(normalized_id)

            if task is None:
                task = asyncio.create_task(self._fetch(normalized_id))
                self._inflight[normalized_id] = task

        try:
            resolved = await task
        finally:
            async with self._lock:
                if self._inflight.get(normalized_id) is task:
                    self._inflight.pop(normalized_id, None)

        linked_parents = normalized_fallback if resolved is None else normalize_parent_ids(resolved)

        async with self._lock:
            self._cache[normalized_id] = linked_parents

        return list(linked_parents)

    def clear(self) -> None:
        """Clear the in-memory parent cache."""
        self._cache.clear()
        self._inflight.clear()
