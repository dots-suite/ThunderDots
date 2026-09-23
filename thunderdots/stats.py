# -*- coding: utf-8 -*-
"""stats.py

Stats collection and reporting for ThunderDots.
"""

import time
from datetime import datetime, timezone


class Stats:
    def __init__(self):
        """Initialize stats with default values.

        - `timestamp`: ISO 8601 UTC timestamp of when the fetch started (e.g.
          ``2026-09-24T10:00:00.123456+00:00``)
        - `elapsed`: Total elapsed time in seconds for the operation
        - `http_errors`: Total number of HTTP errors encountered
        - `requests_total`: Total number of HTTP requests made
        - `requests_skipped`: Number of requests avoided thanks to DTS member hints
          (complete member descriptions, ``totalParents``)
        - `timeouts`: Total number of HTTP requests that timed out
        - `http_500`: Total number of HTTP 500 errors encountered
        """
        self.timestamp = None
        self.elapsed = 0
        self.http_errors = 0
        self.requests_total = 0
        self.requests_skipped = 0
        self.timeouts = 0
        self.http_500 = 0

    def start(self):
        """Start the timer and set the timestamp for when the stats collection begins."""

        self.t0 = time.time()
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.http_errors = 0
        self.requests_total = 0
        self.requests_skipped = 0
        self.timeouts = 0
        self.http_500 = 0

    def stop(self):
        """Stop the timer and calculate the total elapsed time for the operation."""
        self.elapsed = time.time() - self.t0

    def to_dict(self):
        """Convert the collected stats into a dictionary format for reporting or output."""
        return {
            "timestamp": self.timestamp,
            "elapsed_seconds": self.elapsed,
            "http_errors": self.http_errors,
            "requests_total": self.requests_total,
            "requests_skipped": self.requests_skipped,
            "timeouts": self.timeouts,
            "http_500": self.http_500,
        }
