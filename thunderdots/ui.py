# -*- coding: utf-8 -*-

"""ui.py

UI and progress reporting for ThunderDots.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Column
from rich.theme import Theme

theme = Theme(
    {
        "td": "bold cyan",
        "ok": "bold green",
        "logo": "bold cyan",
        "step": "bold magenta",
        "warn": "yellow",
        "err": "bold red",
        "dim": "dim",
    }
)

console = Console(theme=theme)

_LOGO = "[logo]⚡ ThunderDots[/logo]"


@dataclass
class UI:
    """UI and progress reporting for ThunderDots, using rich for console output and progress bars.

    - enabled: Whether to enable UI output (default: True)
    - progress: Optional Progress instance for managing progress bars (initialized in __enter__)
    - task_walk: Optional task ID for the collection walking progress bar
    - task_res: Optional task ID for the resource fetching progress bar
    """

    enabled: bool = True
    progress: Optional[Progress] = None
    task_walk: Optional[int] = None
    task_res: Optional[int] = None

    def __enter__(self):
        """Initialize the Progress instance for managing progress bars if UI is enabled, and return self for use in a with statement."""
        if not self.enabled:
            return self

        console.print()
        console.print(f"  {_LOGO}", highlight=False)
        console.print("  [dim]" + "─" * 28 + "[/dim]")
        console.print()

        self.progress = Progress(
            TextColumn("  "),
            SpinnerColumn(spinner_name="dots", style="cyan"),
            TextColumn("{task.description}", table_column=Column(min_width=36)),
            BarColumn(
                bar_width=22,
                style="dim",
                complete_style="cyan",
                finished_style="green",
            ),
            MofNCompleteColumn(),
            TextColumn("[dim] · [/dim]"),
            TimeElapsedColumn(),
            console=console,
            transient=False,
            disable=not console.is_terminal,
        )
        self.progress.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        """Clean up the Progress instance if it was initialized, ensuring that any progress bars are properly finalized and resources are released when exiting the with statement."""
        if self.progress:
            self.progress.__exit__(exc_type, exc, tb)

    async def __aenter__(self):
        """Asynchronous context manager entry point — calls __enter__."""
        return self.__enter__()

    async def __aexit__(self, exc_type, exc, tb):
        """Asynchronous context manager exit point — calls __exit__."""
        return self.__exit__(exc_type, exc, tb)

    def debug(self, msg: str):
        """Log a debug message with dim styling, only if UI is enabled."""
        self.log(msg, style="dim")

    def warn(self, msg: str):
        """Log a warning message with yellow styling, only if UI is enabled."""
        self.log(msg, style="warn")

    def error(self, msg: str):
        """Log an error message with red styling, only if UI is enabled."""
        self.log(msg, style="err")

    def log(self, msg: str, style: str = "td"):
        """Log a message with the specified style, only if UI is enabled."""
        if self.enabled:
            console.print(msg, style=style)

    def start_walk(self):
        """Start an indeterminate progress bar for the collection-walk phase."""
        if self.progress:
            self.task_walk = self.progress.add_task(
                "  [step]Walk[/step]  [dim]starting…[/dim]",
                total=None,
            )

    def update_collections(self, walked: int, collections: int, resources: int, http_errors: int):
        """Update the walk progress bar with current discovery counts.

        :param walked: Number of DTS objects walked so far.
        :param collections: Collections found so far.
        :param resources: Resources discovered so far.
        :param http_errors: HTTP errors encountered so far.
        """
        if not self.progress or self.task_walk is None:
            return

        err_part = f"  [err]{http_errors} err[/err]" if http_errors else ""
        desc = (
            f"  [step]Walk[/step]  "
            f"[dim]{walked} walked · "
            f"{collections} col · "
            f"{resources} res[/dim]"
            f"{err_part}"
        )
        self.progress.update(self.task_walk, description=desc)

    def finish_walk(self):
        """Mark the walk phase as complete (switches bar to determinate green)."""
        if self.progress and self.task_walk is not None:
            self.progress.update(self.task_walk, total=1, completed=1)

    def start_resources(self, total: int):
        """Start a determinate progress bar for the resource-fetch phase."""
        if self.progress:
            self.task_res = self.progress.add_task(
                "  [step]Fetch[/step]  [dim]starting…[/dim]",
                total=total,
            )

    def update_resources(self, done: int, total: int, http_errors: int):
        """Update the fetch progress bar with current completion state."""
        if not self.progress or self.task_res is None:
            return
        err_part = f"  [err]{http_errors} err[/err]" if http_errors else ""
        desc = f"  [step]Fetch[/step]{err_part}"
        self.progress.update(self.task_res, description=desc, completed=done, total=total)

    def advance_resources(self, n: int = 1):
        """Advance the fetch progress bar by n steps."""
        if self.progress and self.task_res is not None:
            self.progress.advance(self.task_res, n)

    def finalize(self, stats: dict):
        """Print the final summary line after the progress bar has closed."""
        if not self.enabled:
            return

        elapsed = stats.get("elapsed_seconds", 0)
        errors = stats.get("http_errors", 0)
        requests = stats.get("requests_total", 0)

        if errors:
            status = f"[err]✘  {errors} error{'s' if errors > 1 else ''}[/err]"
        else:
            status = "[ok]✔  Done[/ok]"

        console.print()
        console.print(
            f"  {status}  [dim]{elapsed:.2f}s · {requests} req[/dim]",
        )
        console.print()
