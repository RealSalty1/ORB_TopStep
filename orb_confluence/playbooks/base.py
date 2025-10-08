"""Base playbook abstraction for ORB 2.0.

Defines interface that all playbooks must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class ExitMode(str, Enum):
    """Exit mode types."""
    TRAIL_VOL = "TRAIL_VOL"  # ATR-based trailing
    TRAIL_PIVOT = "TRAIL_PIVOT"  # Pivot-based trailing
    HYBRID_VOL_PIVOT = "HYBRID_VOL_PIVOT"  # Hybrid approach
    SINGLE_TARGET = "SINGLE_TARGET"  # Fixed target (reversion)
    PARTIAL_THEN_TRAIL = "PARTIAL_THEN_TRAIL"  # Partial exit then trail
    TIME_DECAY_FORCE = "TIME_DECAY_FORCE"  # Force exit on time decay


@dataclass
class ExitModeDescriptor:
    """Describes preferred exit mode for a signal."""
    
    mode: ExitMode
    
    # Mode-specific parameters
    partial_size: Optional[float] = None  # For PARTIAL_THEN_TRAIL
    partial_at_r: Optional[float] = None
    trail_factor: Optional[float] = None  # For TRAIL_VOL
    time_limit_minutes: Optional[int] = None  # For TIME_DECAY_FORCE
    
    def __repr__(self) -> str:
        """String representation."""
        return f"ExitMode({self.mode.value})"


@dataclass
class SignalMetadata:
    """Metadata accompanying a trade signal."""
    
    # Auction context
    auction_state: str
    auction_state_confidence: float
    
    # OR characteristics
    or_width_norm: float
    breakout_delay_minutes: float
    
    # Volume/volatility
    volume_quality_score: float
    normalized_vol: float
    
    # Directional factors
    drive_energy: float
    rotations: int
    
    # Gap context
    gap_type: str
    
    # Probability (if available)
    p_extension: Optional[float] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "auction_state": self.auction_state,
            "auction_state_confidence": self.auction_state_confidence,
            "or_width_norm": self.or_width_norm,
            "breakout_delay_minutes": self.breakout_delay_minutes,
            "volume_quality_score": self.volume_quality_score,
            "normalized_vol": self.normalized_vol,
            "drive_energy": self.drive_energy,
            "rotations": self.rotations,
            "gap_type": self.gap_type,
            "p_extension": self.p_extension,
        }


@dataclass
class CandidateSignal:
    """Candidate trade signal from a playbook."""
    
    playbook_name: str
    direction: str  # 'long' or 'short'
    entry_price: float
    trigger_price: float
    buffer_used: float
    
    # Stop logic
    initial_stop: float
    phase1_stop_distance: float  # For two-phase system
    structural_anchor: Optional[float] = None
    
    # Exit preferences
    exit_mode: ExitModeDescriptor = None
    
    # Signal metadata
    metadata: SignalMetadata = None
    
    # Timestamp
    timestamp: datetime = None
    
    # Priority (higher = prefer in conflicts)
    priority: float = 1.0
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"Signal({self.playbook_name}, {self.direction.upper()} @ {self.entry_price:.2f}, "
            f"stop={self.initial_stop:.2f}, exit={self.exit_mode.mode if self.exit_mode else 'N/A'})"
        )


class Playbook(ABC):
    """Abstract base class for all playbooks.
    
    Each playbook implements:
    1. Eligibility check (can this playbook trade in this context?)
    2. Signal generation (produce candidate signals)
    3. Exit mode recommendation
    """
    
    def __init__(self, name: str, config: Optional[Dict] = None) -> None:
        """Initialize playbook.
        
        Args:
            name: Playbook name
            config: Optional configuration dictionary
        """
        self.name = name
        self.config = config or {}
        self.enabled = self.config.get("enabled", True)
    
    @abstractmethod
    def is_eligible(self, context: Dict) -> bool:
        """Check if playbook is eligible given context.
        
        Args:
            context: Dictionary with market context (auction state, features, etc.)
            
        Returns:
            True if playbook can generate signals, False otherwise
        """
        pass
    
    @abstractmethod
    def generate_signals(self, context: Dict) -> List[CandidateSignal]:
        """Generate candidate trade signals.
        
        Args:
            context: Dictionary with market context
            
        Returns:
            List of CandidateSignal objects (can be empty)
        """
        pass
    
    @abstractmethod
    def preferred_exit_mode(self, context: Dict) -> ExitModeDescriptor:
        """Recommend exit mode for this playbook in given context.
        
        Args:
            context: Dictionary with market context
            
        Returns:
            ExitModeDescriptor with exit preferences
        """
        pass
    
    def __repr__(self) -> str:
        """String representation."""
        status = "ENABLED" if self.enabled else "DISABLED"
        return f"{self.name} [{status}]"

