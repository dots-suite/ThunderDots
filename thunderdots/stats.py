#-*- coding: utf-8 -*-
"""stats.py

Stats collection and reporting for ThunderDots.
"""
import time
from datetime import datetime

class Stats:
    """Stats collection and reporting for ThunderDots."""
    def start(self):
        """Start the timer and initialize stats."""
        self.t0 = time.time()
        self.timestamp = datetime.utcnow().isoformat()
        self.http_errors = 0  # ← ICI

    def stop(self):
        """Stop the timer and calculate elapsed time."""
        self.elapsed = time.time() - self.t0

    def to_dict(self):
        """Convert stats to a dict for output."""
        return {
            "timestamp": self.timestamp,
            "elapsed_seconds": getattr(self, "elapsed", 0),
            "http_errors": self.http_errors,
        }
