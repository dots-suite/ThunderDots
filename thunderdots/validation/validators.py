from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

from .models import BatchValidationReport, ValidationIssue, ValidationReport
from .schemas import SCHEMAS


def _jsonschema_path(error) -> str:
    return ".".join(str(part) for part in error.absolute_path)


def validate_with_jsonschema(data: dict[str, Any], profile: str) -> ValidationReport:
    schema = SCHEMAS[profile]
    validator = Draft202012Validator(schema)

    issues: list[ValidationIssue] = []
    for error in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
        issues.append(
            ValidationIssue(
                level="error",
                code="jsonschema_error",
                message=error.message,
                path=_jsonschema_path(error) or None,
                expected=str(error.schema),
                actual=repr(error.instance),
            )
        )

    return ValidationReport(
        ok=not issues,
        issues=issues,
    )


def infer_profile(data: dict[str, Any]) -> str:
    if "resource_results" in data and "collection_results" in data:
        return "output"

    typ = data.get("@type")
    if typ == "Collection":
        return "collection"
    if typ == "Resource":
        return "resource"

    if "fragments" in data and "metadata" in data:
        return "resource_result"

    return "resource_result"


def validate_notice(data: dict[str, Any], profile: str | None = None) -> ValidationReport:
    return validate_with_jsonschema(data, profile or infer_profile(data))


def validate_many(items: list[dict[str, Any]], profile: str | None = None) -> BatchValidationReport:
    return BatchValidationReport(reports=[validate_notice(item, profile=profile) for item in items])
