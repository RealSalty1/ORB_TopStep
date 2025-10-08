"""Risk management modules for ORB 2.0.

Includes:
- Two-phase stop system
- Salvage abort logic
- Trailing stop modes
- Partial exits
- Time decay exits
- Position sizing
"""

from .two_phase_stop import (
    StopPhase,
    TwoPhaseStopManager,
    StopUpdate,
)
from .salvage import (
    SalvageConditions,
    SalvageManager,
    SalvageEvent,
)
from .trailing_modes import (
    TrailUpdate,
    VolatilityTrailingStop,
    PivotTrailingStop,
    HybridTrailingStop,
    TrailingStopManager,
)
from .partial_exits import (
    PartialTarget,
    PartialFillEvent,
    PartialExitManager,
    TimeDecayExitManager,
)

__all__ = [
    "StopPhase",
    "TwoPhaseStopManager",
    "StopUpdate",
    "SalvageConditions",
    "SalvageManager",
    "SalvageEvent",
    "TrailUpdate",
    "VolatilityTrailingStop",
    "PivotTrailingStop",
    "HybridTrailingStop",
    "TrailingStopManager",
    "PartialTarget",
    "PartialFillEvent",
    "PartialExitManager",
    "TimeDecayExitManager",
]

