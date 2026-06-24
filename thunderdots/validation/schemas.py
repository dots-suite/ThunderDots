# -*- coding: utf-8 -*-

"""schemas.py

JSON Schemas for validating collections, resources, and output structure.
"""

from __future__ import annotations

LINKED_PARENTS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "string",
        "minLength": 0,
    },
    "uniqueItems": True,
}

COLLECTION_SCHEMA = {
    "type": "object",
    "required": ["@id", "@type"],
    "properties": {
        "@id": {"type": "string"},
        "@type": {
            "type": "string",
            "enum": ["Collection", "Resource"],
        },
        "title": {"type": ["string", "null"]},
        "member": {"type": "array"},
        "totalItems": {"type": ["integer", "null"]},
        "dublinCore": {"type": ["object", "null"]},
        "dublincore": {"type": ["object", "null"]},
        "extensions": {"type": ["object", "null"]},
    },
    "additionalProperties": True,
}

RESOURCE_SCHEMA = {
    "type": "object",
    "required": ["@id", "@type"],
    "properties": {
        "@id": {"type": "string"},
        "@type": {"type": "string"},
        "title": {"type": ["string", "null"]},
        "document": {"type": ["string", "null"]},
        "navigation": {"type": ["string", "null"]},
        "download": {"type": ["object", "array", "null"]},
        "mediaTypes": {"type": ["array", "null"]},
        "citationTrees": {"type": ["object", "null"]},
        "dublinCore": {"type": ["object", "null"]},
        "dublincore": {"type": ["object", "null"]},
        "extensions": {"type": ["object", "null"]},
    },
    "additionalProperties": True,
}

FRAGMENT_SCHEMA = {
    "type": "object",
    "required": ["id", "content"],
    "properties": {
        "id": {"type": "string"},
        "content": {"type": "string"},
        "head": {"type": ["string", "null"]},
        "breadcrumb": {"type": ["string", "null"]},
        "level": {"type": ["integer", "string", "null"]},
    },
    "additionalProperties": True,
}

RESOURCE_RESULT_SCHEMA = {
    "type": "object",
    "required": ["id", "metadata", "fragments"],
    "properties": {
        "id": {"type": "string"},
        "title": {"type": ["string", "null"]},
        "linked_parents": LINKED_PARENTS_SCHEMA,
        "metadata": {"type": "object"},
        "fragments": {
            "type": "array",
            "items": FRAGMENT_SCHEMA,
        },
    },
    "additionalProperties": True,
}

COLLECTION_RESULT_SCHEMA = {
    "type": "object",
    "required": [
        "@id",
        "@type",
        "linked_parents",
        "metadata",
        "member",
    ],
    "properties": {
        "@id": {
            "type": ["string", "null"],
        },
        "@type": {
            "type": ["string", "null"],
        },
        "title": {
            "type": ["string", "null"],
        },
        "linked_parents": LINKED_PARENTS_SCHEMA,
        "metadata": {
            "type": "object",
        },
        "member": {
            "type": "array",
        },
    },
    "additionalProperties": True,
}

OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["dtsVersion", "type", "meta", "collection_results", "resource_results"],
    "properties": {
        "dtsVersion": {"type": "string"},
        "type": {"type": "string"},
        "meta": {"type": "object"},
        "collection_results": {
            "type": "array",
            "items": COLLECTION_RESULT_SCHEMA,
        },
        "resource_results": {
            "type": "array",
            "items": RESOURCE_RESULT_SCHEMA,
        },
    },
    "additionalProperties": True,
}

SCHEMAS = {
    "collection": COLLECTION_SCHEMA,
    "resource": RESOURCE_SCHEMA,
    "resource_result": RESOURCE_RESULT_SCHEMA,
    "output": OUTPUT_SCHEMA,
}
