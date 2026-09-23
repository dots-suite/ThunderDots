# -*- coding: utf-8 -*-
"""config.py

Configuration dataclasses for ThunderDots, with helper methods to create instances from dicts and ensure list fields are properly handled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import warnings

from typing import Any


def _as_list(x: Any) -> list[str]:
    """Convert the input to a list of strings, handling None, single strings, and lists.

    :param x: The input value to convert to a list of strings. Can be None, a single string, or a list of strings.
    :type x: Any
    :return: A list of strings based on the input value. If the input is None
    or an empty string, an empty list is returned. If the input is a single string, a list containing that string is returned. If the input is a list, each element is converted to a string and returned as a list.
    :rtype: list[str]
    """
    if x is None:
        return []

    if isinstance(x, str):
        return [x]

    if isinstance(x, list):
        return [str(v) for v in x]

    return [str(v) for v in list(x)]


def _optional_list(d: dict[str, Any], key: str) -> list[str] | None:
    """Get a list of strings from the dictionary for the given key, or return None if the key is not present.

    :param d: The input dictionary to get the value from
    :type d: dict[str, Any]
    :param key: The key to look up in the dictionary
    :type key: str
    :return: A list of strings if the key is present in the dictionary, or None if the key is not present. If the key is present but the value is None or an empty string, an empty list is returned.
    :rtype: list[str] | None
    """
    if key not in d:
        return None
    return _as_list(d.get(key))


def _split_legacy_metadata_paths(paths: list[str]) -> tuple[list[str], list[str]]:
    """Split legacy metadata paths into dublincore and extensions lists based on their prefixes.
    - Paths starting with dublincore. or dublinCore. are added to the dublincore list (with the prefix removed).
    - Paths starting with extensions. or dct: are added to the extensions list (with the prefix removed for extensions. but not for dct:).

    :param paths: A list of metadata paths to split, where each path is a string that may start with dublincore., dublinCore., extensions., or dct:.
    :type paths: list[str]
    :return: A tuple containing two lists: the first list contains the dublincore metadata paths (with prefixes removed), and the second list contains the extension metadata paths (with "extensions." prefix removed but "dct:" prefix retained).
    :rtype: tuple[list[str], list[str]]
    """
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
    """Parameters for fetching and processing collections, including which metadata fields to keep and which resource IDs to exclude."""

    collection_id: str | None = None
    excluded_ids: list[str] = field(default_factory=list)
    metadata_dublincore: list[str] | None = None
    metadata_extensions: list[str] | None = None
    fetch_linked_parents: bool = True
    # Request-reduction hints read from the ``member`` entries of a collection:
    # - trust_member_metadata: use a Resource member entry as its full description instead
    #   of requesting ``/collection?id=<member>``. ``"auto"`` only does so when the entry
    #   looks complete (``citationTrees`` or ``document`` present, metadata present, and
    #   every explicitly requested metadata key available). ``True`` always trusts it,
    #   ``False`` always fetches.
    # - trust_total_parents: skip ``/collection?id=<x>&nav=parents`` when the member entry
    #   says ``totalParents == 1`` and the traversal already knows that parent.
    trust_member_metadata: bool | str = "auto"
    trust_total_parents: bool = True

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "CollectionParams":
        """Create a CollectionParams instance from a dictionary, handling deprecated 'keep_metadata' and splitting it into dublincore and extensions lists if present.

            :param d: The input dictionary containing configuration parameters for collections. May include keys like 'collection_id', 'excluded_ids', 'metadata_dublincore', 'metadata_extensions', and the deprecated 'keep_metadata'.
            :type d: dict[str, Any] | None
            :return: A CollectionParams instance populated with the values from the input dictionary, with proper
        handling of list fields and deprecated 'keep_metadata'.
            :rtype: CollectionParams
        """
        d = d or {}

        if d.get("keep_metadata"):
            warnings.warn(
                "'keep_metadata' is deprecated. Use 'metadata_dublincore' and "
                "'metadata_extensions' instead.",
                DeprecationWarning,
                stacklevel=2,
            )

        legacy_dc, legacy_ext = _split_legacy_metadata_paths(_as_list(d.get("keep_metadata")))
        # metadata_dublincore = _optional_list(d, "metadata_dublincore")
        # metadata_extensions = _optional_list(d, "metadata_extensions")
        metadata_dublincore = d.get("metadata_dublincore") if d is not None else None
        metadata_extensions = d.get("metadata_extensions") if d is not None else None

        trust_member_metadata = d.get("trust_member_metadata", "auto")
        if isinstance(trust_member_metadata, str):
            trust_member_metadata = trust_member_metadata.strip().lower()
            if trust_member_metadata != "auto":
                raise ValueError(
                    "collection_params.trust_member_metadata must be True, False or 'auto', "
                    f"got {d.get('trust_member_metadata')!r}"
                )
        elif not isinstance(trust_member_metadata, bool):
            raise ValueError(
                "collection_params.trust_member_metadata must be True, False or 'auto', "
                f"got {trust_member_metadata!r}"
            )

        return cls(
            collection_id=d.get("collection_id"),
            excluded_ids=_as_list(d.get("excluded_ids")),
            metadata_dublincore=(
                metadata_dublincore if metadata_dublincore is not None else legacy_dc or None
            ),
            metadata_extensions=(
                metadata_extensions if metadata_extensions is not None else legacy_ext or None
            ),
            fetch_linked_parents=bool(d.get("fetch_linked_parents", True)),
            trust_member_metadata=trust_member_metadata,
            trust_total_parents=bool(d.get("trust_total_parents", True)),
        )


@dataclass(slots=True)
class ResourceParams:
    """Parameters for fetching and processing resources, including which metadata fields to keep, how to handle fragments, and other options related to resource processing."""

    metadata_dublincore: list[str] | None = None
    metadata_extensions: list[str] | None = None
    add_head_to_content: bool = True
    include_breadcrumb: bool = True
    exclude_heads_contains: list[str] = field(default_factory=list)
    fetch_document: bool = True
    fetch_navigation: bool = True
    fetch_linked_parents: bool = True
    fragment_mode: str = "auto"
    fragment_xpath: str | None = None
    title_xpath: str = "./tei:head"
    remove_fragment_heads: bool = True
    generated_id_prefix: str = "__DOCUMENT__"

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "ResourceParams":
        """Create a ResourceParams instance from a dictionary, handling deprecated 'keep_metadata' and splitting it into dublincore and extensions lists if present, as well as properly handling other configuration options.

            :param d: The input dictionary containing configuration parameters for resources. May include keys like 'metadata_dublincore', 'metadata_extensions', 'add_head_to_content', 'include_breadcrumb', 'exclude_heads_contains', 'fetch_document', 'fetch_navigation', 'fragment_mode', 'fragment_xpath', 'title_xpath', 'remove_fragment_heads', 'generated_id_prefix', and the deprecated 'keep_metadata'.
            :type d: dict[str, Any] | None
            :return: A ResourceParams instance populated with the values from the input dictionary, with proper
        handling of list fields, boolean options, and deprecated 'keep_metadata'.
            :rtype: ResourceParams
        """
        d = d or {}
        if d.get("keep_metadata"):
            warnings.warn(
                "'keep_metadata' is deprecated. Use 'metadata_dublincore' and "
                "'metadata_extensions' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        legacy_dc, legacy_ext = _split_legacy_metadata_paths(_as_list(d.get("keep_metadata")))
        # metadata_dublincore = _optional_list(d, "metadata_dublincore")
        # metadata_extensions = _optional_list(d, "metadata_extensions")
        metadata_dublincore = d.get("metadata_dublincore") if d is not None else None
        metadata_extensions = d.get("metadata_extensions") if d is not None else None
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
            fetch_linked_parents=bool(d.get("fetch_linked_parents", True)),
            fragment_mode=str(d.get("fragment_mode", "auto")),
            fragment_xpath=d.get("fragment_xpath"),
            title_xpath=str(d.get("title_xpath", "./tei:head")),
            remove_fragment_heads=bool(d.get("remove_fragment_heads", True)),
            generated_id_prefix=str(d.get("generated_id_prefix", "__DOCUMENT__")),
        )


_FRAGMENT_PARAM_KEYS = (
    "metadata_dublincore",
    "metadata_extensions",
    "temporal_index",
    "temporal_xpath",
)


@dataclass(slots=True)
class FragmentsParams:
    """Parameters controlling the metadata attached to each extracted fragment.

    - ``metadata_dublincore`` / ``metadata_extensions``: Dublin Core and extension fields
      to keep from the DTS navigation member describing the fragment. ``None`` keeps all
      fields, ``[]`` keeps none (same semantics as ``ResourceParams``).
    - ``temporal_xpath``: optional XPath evaluated relative to each fragment node in the
      TEI document (e.g. ``".//tei:docDate/tei:date"``). Matching values are stored under
      ``metadata.tei.date`` so they take part in the fragment temporal index.
    - ``temporal_index``: ``True`` / ``False`` to force the computation of a per-fragment
      ``temporal`` index, or ``"auto"`` (default) to enable it only when fragment metadata
      has been explicitly requested. A fragment without explicit temporal metadata gets an
      empty index: resource-level dates are never inherited.
    - ``requested``: internal flag, ``True`` when the user explicitly passed fragment
      parameters. Set by :meth:`from_dict`.
    """

    metadata_dublincore: list[str] | None = None
    metadata_extensions: list[str] | None = None
    temporal_index: bool | str = "auto"
    temporal_xpath: str | None = None
    requested: bool = False

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "FragmentsParams":
        """Create a FragmentsParams instance from a dictionary.

        :param d: Input dictionary. May contain ``metadata_dublincore``, ``metadata_extensions``,
            ``temporal_index`` and ``temporal_xpath``.
        :type d: dict[str, Any] | None
        :return: A FragmentsParams instance.
        :rtype: FragmentsParams
        :raises ValueError: If ``temporal_index`` is neither a boolean nor ``"auto"``.
        """
        d = d or {}

        temporal_index = d.get("temporal_index", "auto")
        if isinstance(temporal_index, str):
            temporal_index = temporal_index.strip().lower()
            if temporal_index != "auto":
                raise ValueError(
                    "fragment_params.temporal_index must be True, False or 'auto', "
                    f"got {d.get('temporal_index')!r}"
                )
        elif not isinstance(temporal_index, bool):
            raise ValueError(
                "fragment_params.temporal_index must be True, False or 'auto', "
                f"got {temporal_index!r}"
            )

        temporal_xpath = d.get("temporal_xpath")
        temporal_xpath = str(temporal_xpath).strip() or None if temporal_xpath else None

        return cls(
            metadata_dublincore=d.get("metadata_dublincore"),
            metadata_extensions=d.get("metadata_extensions"),
            temporal_index=temporal_index,
            temporal_xpath=temporal_xpath,
            requested=any(key in d for key in _FRAGMENT_PARAM_KEYS),
        )

    @property
    def temporal_index_enabled(self) -> bool:
        """Resolve ``temporal_index`` to a boolean.

        ``"auto"`` enables the per-fragment temporal index when fragment parameters were
        explicitly given and at least one metadata source is kept (a filter set to ``[]``
        keeps nothing, and ``temporal_xpath`` counts as a source).

        :return: True when fragments must carry a ``temporal`` index.
        :rtype: bool
        """
        if isinstance(self.temporal_index, bool):
            return self.temporal_index

        if not self.requested:
            return False

        keeps_dublincore = self.metadata_dublincore is None or bool(self.metadata_dublincore)
        keeps_extensions = self.metadata_extensions is None or bool(self.metadata_extensions)
        return keeps_dublincore or keeps_extensions or bool(self.temporal_xpath)


@dataclass(slots=True)
class ThunderDotsConfig:
    """Configuration for ThunderDots, including endpoint URL, options for fetching metadata, validation settings, parameters for collections and resources, concurrency and timeout settings, and output paths."""

    endpoint_dts: str
    fetch_collection_metadata: bool = True
    fetch_resource_metadata: bool = True
    validate: bool = False
    validation_profile: str = "dts"
    collection_params: CollectionParams = field(default_factory=CollectionParams)
    resource_params: ResourceParams = field(default_factory=ResourceParams)
    fragment_params: FragmentsParams = field(default_factory=FragmentsParams)
    verbose: bool = True
    concurrency: int = 20
    timeout: float = 30.0
    request_timeout: float = 20.0
    retries: int = 2
    backoff_ms: int = 200
    output_path: str | None = None
    cache_csv_path: str | None = None
    use_cache: bool = True
