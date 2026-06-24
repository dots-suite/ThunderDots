#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""ThunderDots sandbox script.

This script compares two DTS fragment retrieval modes:

- ``document``: retrieves each resource as a single full-document fragment.
- ``navigation``: retrieves DTS navigation data and extracts one fragment per
  navigational unit when possible.

The script writes, for each mode:

- a complete JSON output produced by ThunderDots;
- a readable TXT summary;
- a console summary;
- basic HTTP diagnostics;
- a short preview of retrieved resources and fragments.

It is intended as a development and diagnostic script, not as part of the
library public API.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from pprint import pprint
from typing import Any

from thunderdots import ThunderDots


ENDPOINT_DTS = "https://dev.chartes.psl.eu/dots/api/dts"
COLLECTION_ID = "cid"

OUT_DIR = Path("out_results")

HTTP_PARAMS = {
    "concurrency": 20,
    "request_timeout": 10.0,
    "retries": 2,
    "backoff_ms": 300,
}


def now_stamp() -> str:
    """Return a filesystem-friendly timestamp for output file names.

    Returns
    -------
    str
        Current local timestamp formatted as ``YYYYMMDD_HHMMSS``.
    """
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def compact_text(text: str | None, max_chars: int = 500) -> str:
    """Normalize whitespace and truncate text to a maximum number of characters.

    Parameters
    ----------
    text : str | None
        Input text to normalize and truncate. ``None`` is treated as an empty
        string.
    max_chars : int, default=500
        Maximum number of characters to keep.

    Returns
    -------
    str
        Compact text preview. If the text is longer than ``max_chars``, it is
        truncated and suffixed with an ellipsis.
    """
    compacted = " ".join((text or "").split())

    if len(compacted) <= max_chars:
        return compacted

    return compacted[:max_chars].rstrip() + "…"


def print_separator(title: str | None = None) -> None:
    """Print a visual separator, optionally followed by a section title.

    Parameters
    ----------
    title : str | None, optional
        Optional title displayed between separator lines.
    """
    print("\n" + "=" * 100)

    if title:
        print(title)
        print("=" * 100)


def build_client(
    *,
    fragment_mode: str,
    output_json: Path,
    verbose: bool = True,
) -> ThunderDots:
    """Build a configured ThunderDots client for one fragment extraction mode.

    Parameters
    ----------
    fragment_mode : str
        Fragment extraction mode passed to ThunderDots. Expected values include
        ``"document"`` and ``"navigation"``.
    output_json : pathlib.Path
        Path where the full JSON output should be written.
    verbose : bool, default=True
        Whether to display ThunderDots progress output.

    Returns
    -------
    ThunderDots
        Configured ThunderDots client.
    """
    return ThunderDots(
        endpoint_dts=ENDPOINT_DTS,
        collection_params={
            "collection_id": COLLECTION_ID,
            "metadata_dublincore": ["title"],
        },
        resource_params={
            "metadata_dublincore": ["title", "creator", "date", "coverage"],
            "metadata_extensions": ["dct:extend"],
            "fragment_mode": fragment_mode,
            "add_head_to_content": True,
            "include_breadcrumb": True,
        },
        verbose=verbose,
        output_path=str(output_json),
        use_cache=False,
        **HTTP_PARAMS,
    )


def summarize_results(results: dict[str, Any], stats: dict[str, Any]) -> dict[str, Any]:
    """Compute aggregate counts and diagnostics from ThunderDots results.

    Parameters
    ----------
    results : dict[str, Any]
        Result dictionary returned by ``ThunderDots.results()``.
    stats : dict[str, Any]
        Runtime statistics returned by ``ThunderDots.stats()``.

    Returns
    -------
    dict[str, Any]
        Summary containing collection count, collection member count, resource
        count, fragment count, output metadata, and runtime statistics.
    """
    collection_results = results.get("collection_results", [])
    resource_results = results.get("resource_results", [])

    members_count = sum(len(collection.get("member") or []) for collection in collection_results)

    fragments_count = sum(len(resource.get("fragments") or []) for resource in resource_results)

    return {
        "collections": len(collection_results),
        "collection_members": members_count,
        "resources": len(resource_results),
        "fragments": fragments_count,
        "meta": results.get("meta", {}),
        "stats": stats,
    }


def print_summary(mode: str, results: dict[str, Any], stats: dict[str, Any]) -> None:
    """Print a console summary for one fragment retrieval mode.

    Parameters
    ----------
    mode : str
        Fragment retrieval mode used for the run.
    results : dict[str, Any]
        Result dictionary returned by ``ThunderDots.results()``.
    stats : dict[str, Any]
        Runtime statistics returned by ``ThunderDots.stats()``.
    """
    summary = summarize_results(results, stats)

    print_separator(f"Summary — fragment_mode={mode!r}")
    print(f"Collections        : {summary['collections']}")
    print(f"Collection members : {summary['collection_members']}")
    print(f"Retrieved resources: {summary['resources']}")
    print(f"Retrieved fragments: {summary['fragments']}")

    print("\nMeta:")
    pprint(summary["meta"], sort_dicts=False)

    print("\nStats:")
    pprint(summary["stats"], sort_dicts=False)

    if summary["collection_members"] and not summary["resources"]:
        print("\n⚠️  Likely diagnostic:")
        print(
            "The collection was retrieved successfully, but no resource was fetched. "
            "The document retrieval mode probably failed for every collection member."
        )


def print_first_items(results: dict[str, Any], *, limit: int = 3) -> None:
    """Print a short preview of the first retrieved resources and fragments.

    Parameters
    ----------
    results : dict[str, Any]
        Result dictionary returned by ``ThunderDots.results()``.
    limit : int, default=3
        Maximum number of resources to preview.
    """
    resources = results.get("resource_results", [])

    print_separator(f"Preview of the first {limit} resources")

    if not resources:
        print("No resource retrieved.")
        return

    for index, resource in enumerate(resources[:limit], start=1):
        fragments = resource.get("fragments") or []
        metadata = resource.get("metadata") or {}

        print(f"\n[{index}] {resource.get('id')}")
        print(f"    Title    : {resource.get('title')}")
        print(f"    Fragments: {len(fragments)}")
        print("    Metadata :")
        pprint(metadata, sort_dicts=False, width=120)

        if fragments:
            first_fragment = fragments[0]
            print("    First fragment:")
            print(f"      id   : {first_fragment.get('id')}")
            print(f"      level     : {first_fragment.get('level')}")
            print(f"      head      : {first_fragment.get('head')}")
            print(f"      breadcrumb: {first_fragment.get('breadcrumb')}")
            print(f"      content   : {compact_text(first_fragment.get('content'), 400)}")


def write_summary_txt(
    *,
    mode: str,
    results: dict[str, Any],
    stats: dict[str, Any],
    out_path: Path,
) -> None:
    """Write a readable TXT summary for one ThunderDots run.

    Parameters
    ----------
    mode : str
        Fragment retrieval mode used for the run.
    results : dict[str, Any]
        Result dictionary returned by ``ThunderDots.results()``.
    stats : dict[str, Any]
        Runtime statistics returned by ``ThunderDots.stats()``.
    out_path : pathlib.Path
        Destination path for the TXT summary.
    """
    summary = summarize_results(results, stats)
    resources = results.get("resource_results", [])

    lines: list[str] = []

    lines.append(f"ThunderDots summary — fragment_mode={mode!r}")
    lines.append("=" * 100)
    lines.append(f"Collections        : {summary['collections']}")
    lines.append(f"Collection members : {summary['collection_members']}")
    lines.append(f"Retrieved resources: {summary['resources']}")
    lines.append(f"Retrieved fragments: {summary['fragments']}")
    lines.append("")
    lines.append("Meta")
    lines.append("-" * 100)
    lines.append(json.dumps(summary["meta"], ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("Stats")
    lines.append("-" * 100)
    lines.append(json.dumps(summary["stats"], ensure_ascii=False, indent=2))
    lines.append("")

    if not resources:
        lines.append("No resource retrieved.")
        lines.append("")
        lines.append("Likely diagnostic")
        lines.append("-" * 100)
        lines.append(
            "The collection was retrieved successfully, but resource fetching failed. "
            "This suggests that the selected document retrieval mode is not compatible "
            "with this endpoint or with these resources."
        )

    for resource in resources:
        fragments = resource.get("fragments") or []

        lines.append("=" * 100)
        lines.append(f"ID       : {resource.get('id')}")
        lines.append(f"Title    : {resource.get('title')}")
        lines.append(f"Fragments: {len(fragments)}")

        metadata = resource.get("metadata") or {}
        if metadata:
            lines.append("Metadata")
            lines.append(json.dumps(metadata, ensure_ascii=False, indent=2))

        for index, fragment in enumerate(fragments, start=1):
            lines.append("-" * 100)
            lines.append(f"Fragment {index}")
            lines.append(f"id   : {fragment.get('id')}")
            lines.append(f"level     : {fragment.get('level')}")
            lines.append(f"head      : {fragment.get('head')}")
            lines.append(f"breadcrumb: {fragment.get('breadcrumb')}")
            lines.append("")
            lines.append(compact_text(fragment.get("content"), 1200))
            lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def run_mode(fragment_mode: str, stamp: str) -> dict[str, Any]:
    """Run ThunderDots for one fragment extraction mode.

    Parameters
    ----------
    fragment_mode : str
        Fragment extraction mode to test.
    stamp : str
        Timestamp used to generate output file names.

    Returns
    -------
    dict[str, Any]
        Run record containing the mode, results, stats, and output paths.

    Raises
    ------
    Exception
        Re-raises any exception produced by ``ThunderDots.fetch()`` after
        printing a short diagnostic message.
    """
    output_json = OUT_DIR / f"thunderdots_{fragment_mode}_{stamp}.json"
    output_txt = OUT_DIR / f"thunderdots_{fragment_mode}_{stamp}.txt"

    td = build_client(
        fragment_mode=fragment_mode,
        output_json=output_json,
        verbose=True,
    )

    print_separator(f"Running ThunderDots — fragment_mode={fragment_mode!r}")

    try:
        td.fetch()
    except Exception as exc:
        print(f"❌ Error during td.fetch() for mode={fragment_mode!r}")
        print(type(exc).__name__, exc)
        raise

    results = td.results()
    stats = td.stats()

    print_summary(fragment_mode, results, stats)
    print_first_items(results, limit=3)

    write_summary_txt(
        mode=fragment_mode,
        results=results,
        stats=stats,
        out_path=output_txt,
    )

    print_separator(f"Files written — fragment_mode={fragment_mode!r}")
    print(f"JSON: {output_json}")
    print(f"TXT : {output_txt}")

    return {
        "mode": fragment_mode,
        "results": results,
        "stats": stats,
        "output_json": str(output_json),
        "output_txt": str(output_txt),
    }


def compare_modes(runs: list[dict[str, Any]]) -> None:
    """Print a compact comparison table for all completed runs.

    Parameters
    ----------
    runs : list[dict[str, Any]]
        List of run records returned by ``run_mode``.
    """
    print_separator("Mode comparison")

    rows: list[dict[str, Any]] = []

    for run in runs:
        mode = run["mode"]
        results = run["results"]
        stats = run["stats"]
        summary = summarize_results(results, stats)

        meta = summary["meta"]

        rows.append(
            {
                "mode": mode,
                "collections": summary["collections"],
                "members": summary["collection_members"],
                "resources": summary["resources"],
                "fragments": summary["fragments"],
                "requests_total": meta.get("requests_total"),
                "http_errors": meta.get("http_errors"),
                "timeouts": meta.get("timeouts"),
                "http_500": meta.get("http_500"),
            }
        )

    for row in rows:
        print(
            f"{row['mode']:>10} | "
            f"collections={row['collections']} | "
            f"members={row['members']} | "
            f"resources={row['resources']} | "
            f"fragments={row['fragments']} | "
            f"requests={row['requests_total']} | "
            f"http_errors={row['http_errors']} | "
            f"timeouts={row['timeouts']} | "
            f"http_500={row['http_500']}"
        )


def sandbox() -> None:
    """Run the full sandbox comparison workflow.

    The workflow creates the output directory, generates a shared timestamp,
    runs ThunderDots in both ``document`` and ``navigation`` modes, and prints
    a final comparison table.
    """
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    stamp = now_stamp()
    runs = []

    for mode in ["document", "navigation"]:
        run = run_mode(mode, stamp)
        runs.append(run)

    compare_modes(runs)


if __name__ == "__main__":
    sandbox()
