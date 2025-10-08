"""Signal generation: confluence scoring and breakout detection."""

from .scorer import ConfluenceScorer, ConfluenceScore
from .detector import BreakoutDetector, BreakoutSignal

__all__ = [
    "ConfluenceScorer",
    "ConfluenceScore",
    "BreakoutDetector",
    "BreakoutSignal",
]
