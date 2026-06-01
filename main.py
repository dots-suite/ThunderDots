# -*- coding: utf-8 -*-
#!/usr/bin/env python3

"""Sandbox ThunderDots.

Compare les modes de récupération de fragments DTS :
- navigation
- document

Produit :
- JSON complet par mode ;
- résumé console ;
- TXT lisible par mode ;
- diagnostic des erreurs HTTP ;
- aperçu des ressources/fragments récupérés.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from pprint import pprint
from typing import Any

from thunderdots import ThunderDots


ENDPOINT_DTS = "https://dev.chartes.psl.eu/dots/api/dts"
COLLECTION_ID = "ENCPOS_1972"

OUT_DIR = Path("out_results")


HTTP_PARAMS = dict(
    concurrency=8,
    request_timeout=15.0,
    retries=2,
    backoff_ms=300,
)


def now_stamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def compact_text(text: str | None, max_chars: int = 500) -> str:
    text = " ".join((text or "").split())
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "…"


def print_separator(title: str | None = None) -> None:
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
    summary = summarize_results(results, stats)

    print_separator(f"Résumé — fragment_mode={mode!r}")
    print(f"Collections         : {summary['collections']}")
    print(f"Membres collection  : {summary['collection_members']}")
    print(f"Ressources récupérées: {summary['resources']}")
    print(f"Fragments récupérés : {summary['fragments']}")

    print("\nMeta :")
    pprint(summary["meta"], sort_dicts=False)

    print("\nStats :")
    pprint(summary["stats"], sort_dicts=False)

    if summary["collection_members"] and not summary["resources"]:
        print("\n⚠️  Diagnostic probable :")
        print(
            "La collection est bien récupérée, mais aucune ressource ne l’est. "
            "Le mode utilisé pour récupérer les documents échoue probablement "
            "sur chaque membre de la collection."
        )


def print_first_items(results: dict[str, Any], *, limit: int = 3) -> None:
    resources = results.get("resource_results", [])

    print_separator(f"Aperçu des {limit} premières ressources")

    if not resources:
        print("Aucune ressource récupérée.")
        return

    for i, resource in enumerate(resources[:limit], start=1):
        fragments = resource.get("fragments") or []
        metadata = resource.get("metadata") or {}

        print(f"\n[{i}] {resource.get('id')}")
        print(f"    Titre     : {resource.get('title')}")
        print(f"    Fragments : {len(fragments)}")
        print(f"    Metadata  :")
        pprint(metadata, sort_dicts=False, width=120)

        if fragments:
            first_fragment = fragments[0]
            print("    Premier fragment :")
            print(f"      dots_id    : {first_fragment.get('dots_id')}")
            print(f"      level      : {first_fragment.get('level')}")
            print(f"      head       : {first_fragment.get('head')}")
            print(f"      breadcrumb : {first_fragment.get('breadcrumb')}")
            print(f"      content    : {compact_text(first_fragment.get('content'), 400)}")


def write_summary_txt(
    *,
    mode: str,
    results: dict[str, Any],
    stats: dict[str, Any],
    out_path: Path,
) -> None:
    summary = summarize_results(results, stats)
    resources = results.get("resource_results", [])

    lines: list[str] = []

    lines.append(f"ThunderDots — synthèse — fragment_mode={mode!r}")
    lines.append("=" * 100)
    lines.append(f"Collections          : {summary['collections']}")
    lines.append(f"Membres collection   : {summary['collection_members']}")
    lines.append(f"Ressources récupérées: {summary['resources']}")
    lines.append(f"Fragments récupérés  : {summary['fragments']}")
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
        lines.append("Aucune ressource récupérée.")
        lines.append("")
        lines.append("Diagnostic probable")
        lines.append("-" * 100)
        lines.append(
            "La collection a été récupérée, mais les ressources ont échoué. "
            "Cela suggère que le mode de récupération des documents n’est pas "
            "compatible avec cet endpoint ou avec ces ressources."
        )

    for resource in resources:
        fragments = resource.get("fragments") or []

        lines.append("=" * 100)
        lines.append(f"ID        : {resource.get('id')}")
        lines.append(f"Titre     : {resource.get('title')}")
        lines.append(f"Fragments : {len(fragments)}")

        metadata = resource.get("metadata") or {}
        if metadata:
            lines.append("Metadata")
            lines.append(json.dumps(metadata, ensure_ascii=False, indent=2))

        for index, fragment in enumerate(fragments, start=1):
            lines.append("-" * 100)
            lines.append(f"Fragment {index}")
            lines.append(f"dots_id    : {fragment.get('dots_id')}")
            lines.append(f"level      : {fragment.get('level')}")
            lines.append(f"head       : {fragment.get('head')}")
            lines.append(f"breadcrumb : {fragment.get('breadcrumb')}")
            lines.append("")
            lines.append(compact_text(fragment.get("content"), 1200))
            lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def run_mode(fragment_mode: str, stamp: str) -> dict[str, Any]:
    output_json = OUT_DIR / f"thunderdots_{fragment_mode}_{stamp}.json"
    output_txt = OUT_DIR / f"thunderdots_{fragment_mode}_{stamp}.txt"

    td = build_client(
        fragment_mode=fragment_mode,
        output_json=output_json,
        verbose=True,
    )

    print_separator(f"Lancement ThunderDots — fragment_mode={fragment_mode!r}")

    try:
        td.fetch()
    except Exception as exc:
        print(f"❌ Erreur pendant td.fetch() pour mode={fragment_mode!r}")
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

    print_separator(f"Fichiers écrits — fragment_mode={fragment_mode!r}")
    print(f"JSON : {output_json}")
    print(f"TXT  : {output_txt}")

    return {
        "mode": fragment_mode,
        "results": results,
        "stats": stats,
        "output_json": str(output_json),
        "output_txt": str(output_txt),
    }


def compare_modes(runs: list[dict[str, Any]]) -> None:
    print_separator("Comparaison des modes")

    rows = []

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
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    stamp = now_stamp()

    runs = []

    for mode in ["document", "navigation"]:
        run = run_mode(mode, stamp)
        runs.append(run)

    compare_modes(runs)


if __name__ == "__main__":
    sandbox()
