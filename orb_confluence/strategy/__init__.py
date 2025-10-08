"""Strategy modules for ORB confluence.

Includes:
- Confluence scoring
- Breakout signal detection
- Trade state management
- Risk management
- Trade lifecycle management
- Governance rules
"""

from .scoring import (
    compute_score,
    analyze_confluence,
    validate_factor_weights,
    get_factor_contribution,
)
from .breakout import (
    BreakoutSignal,
    detect_breakout,
    check_intrabar_breakout,
    get_breakout_side,
)
from .trade_state import (
    TradeSignal,
    PartialFill,
    ActiveTrade,
)
from .risk import (
    compute_stop,
    build_targets,
    update_be_if_needed,
)
from .trade_manager import (
    TradeManager,
    TradeEvent,
    TradeUpdate,
)
from .governance import (
    GovernanceManager,
    GovernanceState,
)

__all__ = [
    # Scoring
    "compute_score",
    "analyze_confluence",
    "validate_factor_weights",
    "get_factor_contribution",
    # Breakout
    "BreakoutSignal",
    "detect_breakout",
    "check_intrabar_breakout",
    "get_breakout_side",
    # Trade State
    "TradeSignal",
    "PartialFill",
    "ActiveTrade",
    # Risk
    "compute_stop",
    "build_targets",
    "update_be_if_needed",
    # Trade Manager
    "TradeManager",
    "TradeEvent",
    "TradeUpdate",
    # Governance
    "GovernanceManager",
    "GovernanceState",
]