from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


JsonType = Literal["str", "int", "float", "bool", "dict", "list", "null"]


@dataclass(frozen=True, slots=True)
class FieldRule:
    path: str
    required: bool = False
    types: tuple[JsonType, ...] = ()
    allowed_values: tuple[Any, ...] = ()
    description: str = ""


COMMON_RULES = [
    FieldRule("@id", required=True, types=("str",)),
    FieldRule("@type", required=True, types=("str",), allowed_values=("Collection", "Resource")),
    FieldRule("title", required=True, types=("str",)),
]

COLLECTION_RULES = [
    *COMMON_RULES,
    FieldRule("member", required=False, types=("list",)),
    FieldRule("totalItems", required=False, types=("int",)),
    FieldRule("dublinCore", required=False, types=("dict",)),
    FieldRule("extensions", required=False, types=("dict",)),
]

RESOURCE_RULES = [
    *COMMON_RULES,
    FieldRule("document", required=True, types=("str",)),
    FieldRule("navigation", required=True, types=("str",)),
    FieldRule("download", required=False, types=("dict",)),
    FieldRule("mediaTypes", required=False, types=("list",)),
    FieldRule("dublinCore", required=False, types=("dict",)),
    FieldRule("extensions", required=False, types=("dict",)),
]

RESOURCE_RESULT_RULES = [
    FieldRule("id", required=True, types=("str",)),
    FieldRule("title", required=False, types=("str", "null")),
    FieldRule("metadata", required=True, types=("dict",)),
    FieldRule("fragments", required=True, types=("list",)),
]

PROFILES = {
    "collection": COLLECTION_RULES,
    "resource": RESOURCE_RULES,
    "resource_result": RESOURCE_RESULT_RULES,
}
