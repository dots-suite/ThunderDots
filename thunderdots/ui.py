# -- coding: utf-8 -*-
"""ui.py

UI utilities for ThunderDots, using Rich for console output and progress bars.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.theme import Theme

theme = Theme(
    {
        "td": "bold magenta",
        "ok": "green",
        "logo": "bold cyan",
        "warn": "yellow",
        "err": "red",
        "dim": "dim",
    }
)

console = Console(theme=theme)


@dataclass
class UI:
    """UI utilities for ThunderDots, using Rich for console output and progress bars."""

    enabled: bool = True
    progress: Optional[Progress] = None
    task_walk: Optional[int] = None
    task_res: Optional[int] = None

    # ---------------- context managers ---------------- #

    def __enter__(self):
        """Init progress bars if enabled."""
        if not self.enabled:
            return self

        self.progress = Progress(
            SpinnerColumn(style="logo"),
            TextColumn("[logo]⚡ ThunderDots[/logo] [td]{task.description}[/td]"),
            BarColumn(),
            TextColumn("[dim]{task.completed}/{task.total}[/dim]"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
            transient=True,
        )
        self.progress.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        """Stop progress bars if enabled."""
        if self.progress:
            self.progress.__exit__(exc_type, exc, tb)

    async def __aenter__(self):
        """Async context manager entry (just call sync version since Rich doesn't support async natively)."""
        return self.__enter__()

    async def __aexit__(self, exc_type, exc, tb):
        """Async context manager exit (just call sync version since Rich doesn't support async natively)."""
        return self.__exit__(exc_type, exc, tb)

    # ---------------- logging ---------------- #
    def debug(self, msg: str):
        """Log a debug message (dimmed).

        :param msg: Message to log.
        :type msg: str
        """
        self.log(msg, style="dim")

    def warn(self, msg: str):
        """Log a warning message (yellow).

        :param msg: Message to log.
        :type msg: str
        """
        self.log(msg, style="warn")

    def error(self, msg: str):
        """Log an error message (red).

        :param msg: Message to log.
        :type msg: str
        """
        self.log(msg, style="err")

    def log(self, msg: str, style: str = "td"):
        """Log a message with the given style if enabled.

        :param msg: Message to log.
        :type msg: str
        :param style: Style to use for the message (default "td").
        :type style: str
        """
        if self.enabled:
            console.print(msg, style=style)

    # ---------------- walk collections ---------------- #

    def start_walk(self):
        """Init the walk collections progress (just a header, no real progress)."""
        if self.progress:
            # set total=1 to have a single "task" that we can update with stats, without needing to advance it
            self.task_walk = self.progress.add_task("Walk collections", total=1)

    def update_collections(self, walked: int, collections: int, resources: int, http_errors: int):
        """Update the walk collections progress with current stats.

        :param walked: Number of collections walked so far.
        :type walked: int
        :param collections: Number of collections found so far.
        :type collections: int
        :param resources: Number of resources found so far.
        :type resources: int
        :param http_errors: Number of HTTP errors encountered so far.
        :type http_errors: int
        """

        if not self.progress or self.task_walk is None:
            return

        desc = (
            f"Walk collections  "
            f"[dim]walked={walked}  collections={collections}  resources={resources}  "
            f"errors={http_errors}[/dim]"
        )
        # Keep total=1 and just update the description and completed=0 to avoid
        # needing to advance the task, since we are tracking progress via
        # the description and not the completed count
        self.progress.update(self.task_walk, description=desc, completed=0, total=1)

    def finish_walk(self):
        """Mark the walk collections task as completed."""
        if self.progress and self.task_walk is not None:
            self.progress.update(self.task_walk, completed=1)

    # ---------------- fetch resources ---------------- #

    def start_resources(self, total: int):
        """Init the fetch resources progress with the total number of resources to fetch.

        :param total: Total number of resources to fetch.
        :type total: int
        """
        if self.progress:
            self.task_res = self.progress.add_task("Fetch resources", total=total)

    def update_resources(self, done: int, total: int, http_errors: int):
        """Update the fetch resources progress with current stats.

        :param done: Number of resources fetched so far.
        :type done: int
        :param total: Total number of resources to fetch.
        :type total: int
        :param http_errors: Number of HTTP errors encountered so far.
        :type http_errors: int
        """
        if not self.progress or self.task_res is None:
            return
        desc = f"Fetch resources  [dim]errors={http_errors}[/dim]"
        self.progress.update(self.task_res, description=desc, completed=done, total=total)

    def advance_resources(self, n: int = 1):
        """Advance the fetch resources progress by n steps (default 1).

        :param n: Number of steps to advance (default 1).
        :type n: int
        """
        if self.progress and self.task_res is not None:
            self.progress.advance(self.task_res, n)

    # ---------------- finalize ---------------- #

    def finalize(self, stats: dict):
        """Print a final summary message with stats after processing is done.

        :param stats: Stats dict to include in the final message (should contain elapsed_seconds and http_errors).
        :type stats: dict
        """
        if not self.enabled:
            return
        console.print(
            "[logo]⚡ ThunderDots[/logo] "
            f"[ok]✔ Done[/ok]  "
            f"elapsed={stats.get('elapsed_seconds', 0):.2f}s  "
            f"http_errors={stats.get('http_errors', 0)}",
        )
