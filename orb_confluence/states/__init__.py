"""State classification modules for ORB 2.0.

Includes:
- Auction state classification (INITIATIVE, BALANCED, COMPRESSION, etc.)
- Regime detection (volatility regimes)
- Context exclusion matrix
"""

from .auction_state import (
    AuctionState,
    AuctionStateClassifier,
    classify_auction_state,
)
from .context_exclusion import (
    ContextSignature,
    ContextCell,
    ContextExclusionMatrix,
)

__all__ = [
    "AuctionState",
    "AuctionStateClassifier",
    "classify_auction_state",
    "ContextSignature",
    "ContextCell",
    "ContextExclusionMatrix",
]

