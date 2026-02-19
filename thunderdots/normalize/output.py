# -*- coding: utf-8 -*-

"""output.py

Build the final output dict with filtered metadata and results.
"""

from .metadata import keep_paths


def build_output(
    collections: list[tuple[dict, list[str]]],
    resources: list[dict],
    stats: dict,
    version: str,
    keep_collection_meta: list[str] = None,
) -> dict:
    """Build the final output dict with filtered metadata and results.

    :param collections: List of tuples (collection_data, parent_ids) to include in output.
    :type collections: list[tuple[dict, list[str]]]
    :param resources: List of processed resource dicts to include in output.
    :type resources: list[dict]
    :param stats: Stats dict to include in output meta.
    :type stats: dict
    :param version: ThunderDots version string to include in output meta.
    :type version: str
    :param keep_collection_meta: Optional list of dot-separated paths to keep in collection metadata.
    :type keep_collection_meta: list[str], optional
    :return: Final output dict with version, meta, collection_results, and resource_results.
    :rtype: dict
    """
    keep_collection_meta = keep_collection_meta or []

    filtered_collections = []
    for data, parents in collections:
        full_meta = {
            "dublincore": data.get("dublincore", {}) or {},
            "extensions": data.get("extensions", {}) or {},
        }
        meta = keep_paths(full_meta, keep_collection_meta)

        filtered_collections.append(
            {
                "@id": data.get("@id"),
                "@type": data.get("@type"),
                "title": data.get("title"),
                "metadata": {k: v for k, v in meta.items() if v},
                # optionnel: garder seulement les ids des membres
                "member": [
                    {"@id": m.get("@id"), "@type": m.get("@type"), "title": m.get("title")}
                    for m in (data.get("member") or [])
                ],
            }
        )

    return {
        "dtsVersion": "1-alpha",
        "type": "All",
        "meta": {"thunderdots_version": version, **stats.to_dict()},
        "collection_results": filtered_collections,
        "resource_results": resources,
    }
