# -*- coding: utf-8 -*-

"""orm.py

ORM for DotsNotice, with methods to convert to ElasticSearch and Qdrant payloads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from thunderdots.normalize.dates import enrich_temporal_metadata
from thunderdots.normalize.metadata import get_path

import hashlib

DUBLINCORE_DATE_FIELDS = {
    "date",
    "created",
    "issued",
    "coverage",
    "temporal",
    "modified",
}


def stable_int_id(value: str) -> int:
    """Generate a stable integer ID from a string value using SHA-1 hashing. The resulting integer is derived from the first 16 hexadecimal characters of the hash, ensuring a consistent mapping for the same input string.

    :param value: The input string value to generate the integer ID from
    :type value: str
    :return: A stable integer ID derived from the input string
    :rtype: int
    """
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]
    return int(digest, 16)


def flatten_dict(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten a nested dictionary into a single-level dictionary with dotted keys.

    This function recursively flattens a nested dictionary, concatenating keys with dots. For example, {"a": {"b": 1}} becomes {"a.b": 1}. The prefix parameter allows adding a prefix to the keys during recursion.

    :param data: The nested dictionary to flatten
    :type data: dict[str, Any]
    :param prefix: The prefix to add to keys during flattening (used for recursion)
    :type prefix: str, optional
    :return: A flattened dictionary with dotted keys
    :rtype: dict[str, Any]
    """
    flat: dict[str, Any] = {}

    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key

        if isinstance(value, dict):
            flat.update(flatten_dict(value, full_key))
        else:
            flat[full_key] = value

    return flat


def sanitize_payload_key(key: str) -> str:
    """Sanitize a string to be used as a key in a payload by replacing or removing characters that may not be allowed in certain contexts (e.g., Elasticsearch, Qdrant).

    This function replaces dots (.) and colons (:) with double underscores (__), replaces dashes (-) with underscores (_), and removes at signs (@). This ensures that the resulting key is safe to use in contexts where certain characters may have special meanings or restrictions.

    :param key: The input string key to sanitize
    :type key: str
    :return: A sanitized version of the input key, with certain characters replaced or removed
    :rtype: str
    """
    return key.replace(".", "__").replace(":", "__").replace("-", "_").replace("@", "")


@dataclass(slots=True)
class Agent:
    """Represents an agent (e.g., creator) associated with a DotsNotice, with optional fields for ID, type, name, and sameAs links."""

    id: str | None = None
    type: str | None = None
    name: str | None = None
    same_as: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DotsNotice:
    """Represents a notice in the Dots system, with fields for ID, type, title, Dublin Core metadata, extensions, fragments, linked parents, and raw data. Provides methods to convert to ElasticSearch and Qdrant payloads, as well as accessors for metadata and creator agents."""

    id: str
    type: str
    title: str | None = None
    dublincore: dict[str, Any] = field(default_factory=dict)
    extensions: dict[str, Any] = field(default_factory=dict)
    fragments: list[dict[str, Any]] = field(default_factory=list)
    linked_parents: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_resource_result(cls, data: dict[str, Any]) -> "DotsNotice":
        """Create a DotsNotice instance from a resource result dictionary, extracting relevant fields and metadata.

        The method looks for the ID in either "id" or "@id", the type in "@type" (defaulting to "Resource" if not present), and the title in "title". It also extracts Dublin Core metadata and extensions from the "metadata" field, as well as fragments and linked parents from their respective fields. The raw input data is stored in the "raw" field of the DotsNotice instance.

        :param data: The input dictionary representing a resource result, which may contain fields like "id", "@id", "@type", "title", "metadata", "fragments", and "linked_parents".
        :type data: dict[str, Any]
        :return: A DotsNotice instance populated with the extracted data and metadata from the input
        :rtype: DotsNotice
        """
        metadata = data.get("metadata") or {}
        return cls(
            id=str(data.get("id") or data.get("@id")),
            type=str(data.get("@type") or "Resource"),
            title=data.get("title"),
            dublincore=metadata.get("dublincore") or {},
            extensions=metadata.get("extensions") or {},
            fragments=data.get("fragments") or [],
            linked_parents=data.get("linked_parents") or [],
            raw=data,
        )

    @classmethod
    def from_api_notice(cls, data: dict[str, Any]) -> "DotsNotice":
        return cls(
            id=str(data.get("@id")),
            type=str(data.get("@type")),
            title=data.get("title"),
            dublincore=data.get("dublinCore") or data.get("dublincore") or {},
            extensions=data.get("extensions") or {},
            fragments=[],
            linked_parents=[],
            raw=data,
        )

    @property
    def full_text(self) -> str:
        return "\n\n".join(
            str(fragment.get("content") or "").strip()
            for fragment in self.fragments
            if str(fragment.get("content") or "").strip()
        )

    def meta(self, key: str, default: Any = None) -> Any:
        """
        Accès court aux métadonnées Dublin Core.
        Exemple
        -------
        notice.meta("title")
        notice.meta("creator")
        notice.meta("coverage")
        """
        value = get_path(self.dublincore, key)
        return default if value is None else value

    def to_elastic_document(
        self,
        *,
        include_fragments: bool = True,
    ) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "text": self.full_text,
            "dublincore": self.dublincore,
            "extensions": self.extensions,
            "temporal": self.temporal_index,
            "creator_names": self.creator_names,
            "linked_parents": self.linked_parents,
            "metadata_flat": flatten_dict(
                {
                    "dublincore": self.dublincore,
                    "extensions": self.extensions,
                    "temporal": self.temporal_index,
                }
            ),
        }

        if include_fragments:
            payload["fragments"] = self.fragments

        return payload

    def to_elastic_action(
        self,
        *,
        index: str,
        include_fragments: bool = True,
    ) -> dict[str, Any]:
        return {
            "_op_type": "index",
            "_index": index,
            "_id": self.id,
            "_source": self.to_elastic_document(
                include_fragments=include_fragments,
            ),
        }

    def to_qdrant_payload(
        self,
        *,
        include_fragments: bool = True,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        metadata = {
            "dublincore": self.dublincore,
            "extensions": self.extensions,
            "temporal": self.temporal_index,
        }
        metadata_flat = flatten_dict(metadata)

        safe_metadata = {sanitize_payload_key(key): value for key, value in metadata_flat.items()}

        payload = {
            "id": self.id,
            "record_id": self.id,
            "type": self.type,
            "title": self.title,
            "text": self.full_text,
            "creator_names": self.creator_names,
            "linked_parents": self.linked_parents,
            "metadata": metadata,
            "metadata_flat": metadata_flat,
            **safe_metadata,
        }

        if include_fragments:
            payload["fragments"] = self.fragments

        if include_raw:
            payload["raw"] = self.raw

        return payload

    def to_qdrant_point(
        self,
        *,
        vector: list[float] | dict[str, Any] | None = None,
        point_id: int | str | None = None,
        include_fragments: bool = True,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        point = {
            "id": point_id if point_id is not None else stable_int_id(self.id),
            "payload": self.to_qdrant_payload(
                include_fragments=include_fragments,
                include_raw=include_raw,
            ),
        }

        if vector is not None:
            point["vector"] = vector

        return point

    def dc(self, key: str, default: Any = None) -> Any:
        return get_path(self.dublincore, key) or default

    def ext(self, key: str, default: Any = None) -> Any:
        return get_path(self.extensions, key) or default

    @property
    def creator_agents(self) -> list[Agent]:
        value = self.extensions.get("creator")
        if value is None:
            return []

        items = value if isinstance(value, list) else [value]
        agents: list[Agent] = []

        for item in items:
            if isinstance(item, dict):
                same_as = item.get("sameAs") or []
                if isinstance(same_as, str):
                    same_as = [same_as]
                agents.append(
                    Agent(
                        id=item.get("@id"),
                        type=item.get("@type"),
                        name=item.get("name"),
                        same_as=same_as,
                        raw=item,
                    )
                )
            elif isinstance(item, str):
                agents.append(Agent(name=item, raw={"value": item}))

        return agents

    @property
    def creator_names(self) -> list[str]:
        names = [agent.name for agent in self.creator_agents if agent.name]
        if names:
            return names

        dc_creator = self.dc("creator")
        if dc_creator is None:
            return []
        if isinstance(dc_creator, list):
            return [str(v) for v in dc_creator]
        return [str(dc_creator)]

    @property
    def temporal_index(self) -> dict[str, Any]:
        return enrich_temporal_metadata(
            {
                "dublincore": self.dublincore,
                "extensions": self.extensions,
            }
        )

    def to_index_payload(
        self,
        *,
        dublincore_fields: list[str] | None = None,
        extension_fields: list[str] | None = None,
        include_index_text: bool = True,
    ) -> dict[str, Any]:
        dublincore_fields = dublincore_fields or []
        extension_fields = extension_fields or []

        dc_payload = {
            key: get_path(self.dublincore, key)
            for key in dublincore_fields
            if get_path(self.dublincore, key) is not None
        }

        ext_payload = {
            key: get_path(self.extensions, key)
            for key in extension_fields
            if get_path(self.extensions, key) is not None
        }

        payload = {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "dublincore": dc_payload,
            "extensions": ext_payload,
            "temporal": self.temporal_index,
            "creator_names": self.creator_names,
        }

        if include_index_text:
            parts = [
                self.title,
                dc_payload.get("title"),
                dc_payload.get("creator"),
                dc_payload.get("source"),
                " ".join(self.creator_names),
            ]
            payload["index_text"] = " ".join(str(part) for part in parts if part).strip()

        return payload

    def __getattr__(self, name: str) -> Any:
        """
        Permet notice.creator, notice.coverage, notice.issued, etc.
        Uniquement pour les clés présentes dans dublincore ou temporal_index.
        """
        if name in self.dublincore:
            return self.dublincore[name]
        temporal = self.temporal_index_short
        if name in temporal:
            return temporal[name]
        raise AttributeError(name)

    @property
    def temporal_index_short(self) -> dict[str, Any]:
        """
        Version courte :
        coverage, coverage_start, coverage_end, coverage_start_iso, etc.
        """
        return enrich_temporal_metadata(self.dublincore)
