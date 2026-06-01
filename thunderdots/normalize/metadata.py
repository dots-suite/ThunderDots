# thunderdots/normalize/metadata.py

from __future__ import annotations

from typing import Any


MISSING = object()


def canonicalize_metadata_keys(src: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(src, dict):
        return {}

    out = dict(src)

    if "dublincore" not in out and "dublinCore" in out:
        out["dublincore"] = out.pop("dublinCore")

    return out


def get_path(src: dict[str, Any], dotted_path: str) -> Any:
    cur: Any = src
    for part in dotted_path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def set_path(out: dict[str, Any], dotted_path: str, value: Any) -> None:
    cur = out
    parts = dotted_path.split(".")
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def pick_keys(src: dict[str, Any], keys: list[str] | None) -> dict[str, Any]:
    """
    keys=None  -> keep everything
    keys=[]    -> keep nothing
    keys=[...] -> keep selected paths
    """
    if not isinstance(src, dict):
        return {}

    if keys is None:
        return dict(src)

    if not keys:
        return {}

    out: dict[str, Any] = {}
    for key in keys:
        value = get_path(src, key)
        if value is not None:
            set_path(out, key, value)
    return out


def build_metadata(
    raw_notice: dict[str, Any],
    *,
    metadata_dublincore: list[str] | None,
    metadata_extensions: list[str] | None,
) -> dict[str, Any]:
    raw_notice = canonicalize_metadata_keys(raw_notice)

    dc = raw_notice.get("dublincore") or {}
    ext = raw_notice.get("extensions") or {}

    metadata = {
        "dublincore": pick_keys(dc, metadata_dublincore),
        "extensions": pick_keys(ext, metadata_extensions),
    }

    return {key: value for key, value in metadata.items() if value}
