# -*- coding: utf-8 -*-
# !/usr/bin/env python3

"""A sandbox to test
ThunderDots interface.
"""

import os
import datetime
import yappi

from thunderdots import ThunderDots


def sandbox():
    dir = "out_results"
    os.makedirs(dir, exist_ok=True)
    out_filename = (
        f"{dir}/thunderdots_results_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    http_params = dict(
        concurrency=8,
        max_inflight=8 * 2,
        request_timeout=15.0,
        retries=2,
        backoff_ms=300,
    )
    td = ThunderDots(
        endpoint_dts="https://dev.chartes.psl.eu/dots/api/dts",
        collection_params={
            "collection_id": "ENCPOS_2023",
            "keep_metadata": [
                "dublincore.title",
            ],
            # "add_members": True, # opt.
            # "add_hierarchy": True, # opt.
        },
        resource_params={
            "keep_metadata": ["dublincore.creator", "dublincore.date", "extensions.dct:extend"],
            # "add_hierarchy": True, # opt.
            # "add_head_to_content": True, # opt.
        },
        verbose=True,
        fetcher="python",  # "go" | "python"
        output_path=out_filename,
        **http_params,
    )
    # yappi.set_clock_type("wall")
    # yappi.start(builtins=True)
    td.fetch()
    res = td.results()
    print("collections:", len(res.get("collection_results", [])))
    print("resources:", len(res.get("resource_results", [])))
    print("meta:", res.get("meta", {}))
    # yappi.stop()
    # yappi.get_thread_stats().print_all()
    # yappi.get_func_stats().sort("ttot", "desc").print_all()

    # res.collection_results()

    # res.resource_results()

    print(td.stats())


if __name__ == "__main__":
    sandbox()
