# -*- coding: utf-8 -*-

"""validators.py

Validation functions for collections, resources, and output structure using JSON Schema.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from .models import BatchValidationReport, ValidationIssue, ValidationReport
from .schemas import SCHEMAS


@lru_cache(maxsize=None)
def _validator_for(profile: str) -> Any:
    """Return the compiled JSON Schema validator of a profile, built once per process.

    ``jsonschema`` is imported here rather than at module level: it is a heavy import
    (about 400 ms) that only validation runs need.

    :param profile: Profile name, a key of :data:`SCHEMAS`.
    :type profile: str
    :return: A ``Draft202012Validator`` for that profile.
    :rtype: jsonschema.Draft202012Validator
    """
    from jsonschema import Draft202012Validator

    return Draft202012Validator(SCHEMAS[profile])


def _jsonschema_path(error) -> str:
    """Convert the absolute path of a JSON Schema validation error into a dot-separated string representation, which can be used to indicate the location of the error within the JSON structure.

    :param error: The JSON Schema validation error object containing the absolute path to the error location.
    :type error: jsonschema.exceptions.ValidationError
    :return: A dot-separated string representation of the error path, or an empty string if the path is empty.
    :rtype: str
    """
    return ".".join(str(part) for part in error.absolute_path)


def validate_with_jsonschema(data: dict[str, Any], profile: str) -> ValidationReport:
    """Validate the given data against the JSON Schema corresponding to the specified profile, and return a ValidationReport indicating whether the data is valid and any issues found during validation.

    :param data: The input data to validate, represented as a dictionary.
    :type data: dict[str, Any]
    :param profile: The profile name indicating which JSON Schema to use for validation (e.g
    "collection", "resource", "resource_result", "output").
    :type profile: str
    :return: A ValidationReport object containing the validation results, including whether the data is valid
    and a list of any issues found during validation.
    :rtype: ValidationReport
    """
    validator = _validator_for(profile)

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
    """Infer the appropriate validation profile for the given data based on its structure and content, which can be used to determine which JSON Schema to use for validation.

        :param data: The input data to infer the profile for, represented as a dictionary.
        :type data: dict[str, Any]
        :return: The inferred profile name (e.g., "collection", "resource", "
    resource_result", "output") based on the structure and content of the input data.
        :rtype: str
    """
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
    """Validate a single notice (collection or resource) against the appropriate JSON Schema profile, either specified explicitly or inferred from the data structure, and return a ValidationReport indicating the validation results.

    :param data: The input notice data to validate, represented as a dictionary.
    :type data: dict[str, Any]
    :param profile: An optional profile name to specify which JSON Schema to use for validation (
    e.g., "collection", "resource", "resource_result"). If not provided, the profile will be inferred from the data structure.
    :type profile: str | None
    :return: A ValidationReport object containing the validation results for the notice, including whether it
    is valid and a list of any issues found during validation.
    :rtype: ValidationReport
    """
    return validate_with_jsonschema(data, profile or infer_profile(data))


def validate_many(items: list[dict[str, Any]], profile: str | None = None) -> BatchValidationReport:
    """Validate multiple notices (collections or resources) against the appropriate JSON Schema profile, either specified explicitly or inferred from each item's data structure, and return a BatchValidationReport containing the validation results for all items.

        :param items: A list of input notice data dictionaries to validate.
        :type items: list[dict[str, Any]]
        :param profile: An optional profile name to specify which JSON Schema to use for validation of
    all items (e.g., "collection", "resource", "resource_result"). If not provided, the profile will be inferred from each item's data structure.
        :type profile: str | None
        :return: A BatchValidationReport object containing the validation results for all items, including a
    summary of the results and a list of individual ValidationReport objects for each item.
        :rtype: BatchValidationReport
    """
    return BatchValidationReport(reports=[validate_notice(item, profile=profile) for item in items])
