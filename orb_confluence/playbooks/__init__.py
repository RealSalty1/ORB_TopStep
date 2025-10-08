"""Playbook system for ORB 2.0 multi-tactic framework.

Each playbook encapsulates a specific trading logic:
- PB1: Classic ORB (refined with state integration)
- PB2: OR Failure Fade
- PB3: Pullback Continuation
- PB4: Compression Expansion
- PB5: Gap Reversion
- PB6: Spread Alignment (ES/NQ)
"""

from .base import (
    Playbook,
    CandidateSignal,
    ExitModeDescriptor,
    SignalMetadata,
)
from .pb1_orb_refined import ORBRefinedPlaybook
from .pb2_failure_fade import FailureFadePlaybook
from .pb3_pullback_continuation import PullbackContinuationPlaybook

__all__ = [
    "Playbook",
    "CandidateSignal",
    "ExitModeDescriptor",
    "SignalMetadata",
    "ORBRefinedPlaybook",
    "FailureFadePlaybook",
    "PullbackContinuationPlaybook",
]

