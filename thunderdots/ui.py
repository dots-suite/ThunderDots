from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
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
    enabled: bool = True
    progress: Optional[Progress] = None
    task_walk: Optional[int] = None
    task_res: Optional[int] = None

    def __enter__(self):
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
            disable=not console.is_terminal,
        )
        self.progress.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.progress:
            self.progress.__exit__(exc_type, exc, tb)

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, exc_type, exc, tb):
        return self.__exit__(exc_type, exc, tb)

    def debug(self, msg: str):
        self.log(msg, style="dim")

    def warn(self, msg: str):
        self.log(msg, style="warn")

    def error(self, msg: str):
        self.log(msg, style="err")

    def log(self, msg: str, style: str = "td"):
        if self.enabled:
            console.print(msg, style=style)

    def start_walk(self):
        if self.progress:
            self.task_walk = self.progress.add_task("Walk collections", total=1)

    def update_collections(self, walked: int, collections: int, resources: int, http_errors: int):
        if not self.progress or self.task_walk is None:
            return

        desc = (
            f"Walk collections  "
            f"[dim]walked={walked}  collections={collections}  resources={resources}  "
            f"errors={http_errors}[/dim]"
        )
        self.progress.update(self.task_walk, description=desc, completed=0, total=1)

    def finish_walk(self):
        if self.progress and self.task_walk is not None:
            self.progress.update(self.task_walk, completed=1)

    def start_resources(self, total: int):
        if self.progress:
            self.task_res = self.progress.add_task("Fetch resources", total=total)

    def update_resources(self, done: int, total: int, http_errors: int):
        if not self.progress or self.task_res is None:
            return
        desc = f"Fetch resources  [dim]errors={http_errors}[/dim]"
        self.progress.update(self.task_res, description=desc, completed=done, total=total)

    def advance_resources(self, n: int = 1):
        if self.progress and self.task_res is not None:
            self.progress.advance(self.task_res, n)

    def finalize(self, stats: dict):
        if not self.enabled:
            return
        console.print(
            "[logo]⚡ ThunderDots[/logo] "
            f"[ok]✔ Done[/ok]  "
            f"elapsed={stats.get('elapsed_seconds', 0):.2f}s  "
            f"http_errors={stats.get('http_errors', 0)}",
        )
