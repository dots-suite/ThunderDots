# -*- coding: utf-8 -*-
#! usr/bin/env python3

from thunderdots import ThunderDots

HTTP_PARAMS = {
    "concurrency": 20,
    "request_timeout": 10.0,
    "retries": 2,
    "backoff_ms": 300,
}

if __name__ == "__main__":
    # 1 - definir ou est ES
    # 2 - Fetch les collections et ressources DTS via DoTS
    # 3 - Convertir en documents ES via les méthodes thunderdots
    # 4 - bulk import into ES
    td = ThunderDots(
        endpoint_dts="https://dev.chartes.psl.eu/dots/api/dts",
        collection_params={
            "collection_id": "theater",
            "metadata_dublincore": ["title", "creator"],
            "fetch_linked_parents": True,
        },
        resource_params={
            "fragment_mode": "navigation",
            "metadata_dublincore": ["title", "creator", "coverage", "license"],
            "metadata_extensions": ["publisher"],
            "add_head_to_content": False,
            "include_breadcrumb": True,
            "fetch_linked_parents": True,
        },
        fragment_params={
            "metadata_dublincore": None,
        },
        use_cache=False,
        **HTTP_PARAMS,
    )
    td.fetch()
    results = td.results()

    with open("output_theater.json", "w", encoding="utf-8") as f:
        import json

        json.dump(results, f, ensure_ascii=False, indent=2)
