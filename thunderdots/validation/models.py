from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ValidationIssue:
    level: str
    code: str
    message: str
    path: str | None = None
    expected: str | None = None
    actual: str | None = None


@dataclass(slots=True)
class ValidationReport:
    ok: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    triple_count: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "triple_count": self.triple_count,
            "issues": [issue.__dict__ for issue in self.issues],
        }


@dataclass(slots=True)
class BatchValidationReport:
    reports: list[ValidationReport]

    def summary(self) -> dict[str, Any]:
        total = len(self.reports)
        valid = sum(1 for r in self.reports if r.ok)
        issues = sum(len(r.issues) for r in self.reports)
        return {
            "total": total,
            "valid": valid,
            "invalid": total - valid,
            "issues": issues,
        }
