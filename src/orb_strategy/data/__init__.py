"""Data acquisition and management layer.

Provides unified interface for multiple data sources (Yahoo Finance, Binance,
synthetic generators) with consistent schema and caching.
"""

from .base import DataProvider, BarData
from .yahoo_provider import YahooProvider
from .binance_provider import BinanceProvider
from .synthetic_provider import SyntheticProvider
from .data_manager import DataManager

__all__ = [
    "DataProvider",
    "BarData",
    "YahooProvider",
    "BinanceProvider",
    "SyntheticProvider",
    "DataManager",
]
