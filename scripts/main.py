# -*- coding: utf-8 -*-
#! usr/bin/env python3

from thunderdots import ThunderDots

HTTP_PARAMS = {
    "concurrency": 8,
    "request_timeout": 20.0,
    "retries": 2,
    "backoff_ms": 80,
}

if __name__ == "__main__":
    td = ThunderDots(
        endpoint_dts="https://dev.chartes.psl.eu/dots/api/dts",
        collection_params={
            "collection_id": "cartulaires",
            "metadata_dublincore": ["title", "creator"],
            "fetch_linked_parents": True,
        },
        resource_params={
            "fragment_mode": "navigation",
            "metadata_dublincore": ["title", "creator", "issued", "dateCreated", "coverage", "license"],
            "metadata_extensions": ["publisher", "temporalCoverage"],
            "add_head_to_content": False,
            "include_breadcrumb": True,
            # "fetch_linked_parents": True,
        },
        fragment_params={
            "metadata_dublincore": ["title", "date"],
            "metadata_extensions": ["dateCreated"],
        },
        use_cache=True,
        verbose=True,
        **HTTP_PARAMS,
    )
    td.fetch()
    results = td.results()

    notices = td.notices()
    f = open("output_cartulaire_notices.json", "w", encoding="utf-8")
    for notice in notices:
        print(notice.id)
        print(notice.temporal_index)
        f.write(f"Ressource: {notice.id}\n")
        f.write(f"{notice.temporal_index}\n")
        f.write(f"=====================\n")
        fragments = notice.fragments
        f.write(f"Fragments: {len(fragments)}\n")
        for frag in fragments:
            f.write(f"  {frag}\n")

    f.close()

    fragment = td.results()["resource_results"][0]["fragments"]

    with open("output_cartulaire_frag.json", "w", encoding="utf-8") as f:
        import json

        json.dump(fragment, f, ensure_ascii=False, indent=2)
