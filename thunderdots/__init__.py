# -*- coding: utf-8 -*-

from importlib.metadata import PackageNotFoundError, version

from .client import ThunderDots

try:
    __version__ = version("thunderdots")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["ThunderDots", "__version__"]
