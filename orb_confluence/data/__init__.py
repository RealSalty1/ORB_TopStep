"""Data fetching, normalization, and quality control."""

from .sources import YahooProvider, BinanceProvider, SyntheticProvider
from .normalizer import normalize_bars, filter_to_session
from .qc import (
    quality_check,
    detect_gaps,
    check_or_window,
    check_ohlc_validity,
    DayQualityReport,
)

__all__ = [
    # Providers
    "YahooProvider",
    "BinanceProvider",
    "SyntheticProvider",
    # Normalization
    "normalize_bars",
    "filter_to_session",
    # Quality Control
    "quality_check",
    "detect_gaps",
    "check_or_window",
    "check_ohlc_validity",
    "DayQualityReport",
]