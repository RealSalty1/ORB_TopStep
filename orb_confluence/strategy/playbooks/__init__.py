"""Playbook implementations for multi-playbook strategy.

Each playbook is a self-contained trading strategy optimized for specific
market regimes and conditions.

Available Playbooks:
- IBFadePlaybook: Fade weak extensions beyond Initial Balance (Mean Reversion)
- VWAPMagnetPlaybook: Mean reversion to VWAP with dynamic bands (Mean Reversion)
- MomentumContinuationPlaybook: Trend continuation with pullback entries (Momentum)
- OpeningDriveReversalPlaybook: Fade weak opening drives (Fade)
"""

from orb_confluence.strategy.playbooks.ib_fade import IBFadePlaybook
from orb_confluence.strategy.playbooks.vwap_magnet import VWAPMagnetPlaybook
from orb_confluence.strategy.playbooks.momentum_continuation import MomentumContinuationPlaybook
from orb_confluence.strategy.playbooks.opening_drive_reversal import OpeningDriveReversalPlaybook

__all__ = [
    'IBFadePlaybook',
    'VWAPMagnetPlaybook',
    'MomentumContinuationPlaybook',
    'OpeningDriveReversalPlaybook',
]

