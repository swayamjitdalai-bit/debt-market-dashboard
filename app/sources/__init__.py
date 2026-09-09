"""Data source adapters. Each exposes plain functions returning normalized dicts."""
from . import cbrics, ccil, fbil, ftrac, market

__all__ = ["cbrics", "ccil", "fbil", "ftrac", "market"]
