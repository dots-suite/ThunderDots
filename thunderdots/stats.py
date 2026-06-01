# -*- coding: utf-8 -*-
"""stats.py

Stats collection and reporting for ThunderDots.
"""

import time
from datetime import datetime


class Stats:
    def __init__(self):
        self.timestamp = None
        self.elapsed = 0
        self.http_errors = 0
        self.requests_total = 0
        self.timeouts = 0
        self.http_500 = 0

    def start(self):
        self.t0 = time.time()
        self.timestamp = datetime.utcnow().isoformat()
        self.http_errors = 0
        self.requests_total = 0
        self.timeouts = 0
        self.http_500 = 0

    def stop(self):
        self.elapsed = time.time() - self.t0

    def to_dict(self):
        return {
            "timestamp": self.timestamp,
            "elapsed_seconds": self.elapsed,
            "http_errors": self.http_errors,
            "requests_total": self.requests_total,
            "timeouts": self.timeouts,
            "http_500": self.http_500,
        }
