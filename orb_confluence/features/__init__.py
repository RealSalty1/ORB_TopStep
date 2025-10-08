"""Feature engineering modules for ORB strategy.

Includes opening range, volume, price action, profile, indicators, and more.
"""

from .opening_range import OpeningRangeBuilder, validate_or, ORState
from .relative_volume import RelativeVolume
from .price_action import analyze_price_action
from .profile_proxy import ProfileProxy
from .vwap import SessionVWAP
from .adx import ADX

# ORB 2.0 components
try:
    from .or_layers import DualORBuilder, DualORState
    from .auction_metrics import AuctionMetricsBuilder, AuctionMetrics, GapType
    from .feature_table import FeatureTableBuilder, FeatureTable
except ImportError:
    # Backwards compatibility
    pass

__all__ = [
    "OpeningRangeBuilder",
    "validate_or",
    "ORState",
    "RelativeVolume",
    "analyze_price_action",
    "ProfileProxy",
    "SessionVWAP",
    "ADX",
    # ORB 2.0
    "DualORBuilder",
    "DualORState",
    "AuctionMetricsBuilder",
    "AuctionMetrics",
    "GapType",
    "FeatureTableBuilder",
    "FeatureTable",
]
