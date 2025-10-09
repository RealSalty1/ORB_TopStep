"""Base classes for multi-playbook strategy architecture.

Defines the abstract base class for all playbooks and supporting data structures.
Each playbook implements specific entry/exit logic for different market regimes.
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
import pandas as pd
from loguru import logger


class Direction(Enum):
    """Trade direction."""
    LONG = "LONG"
    SHORT = "SHORT"


class SignalStrength(Enum):
    """Signal strength classification."""
    WEAK = "WEAK"          # 0-0.4
    MODERATE = "MODERATE"  # 0.4-0.7
    STRONG = "STRONG"      # 0.7-1.0


@dataclass
class ProfitTarget:
    """Profit target definition.
    
    Attributes:
        price: Target price level
        size_pct: Percentage of position to exit (0-1)
        label: Description of this target
        r_multiple: Expected R-multiple at this target
    """
    price: float
    size_pct: float
    label: str
    r_multiple: Optional[float] = None
    
    def __post_init__(self):
        """Validate profit target."""
        if not 0 < self.size_pct <= 1.0:
            raise ValueError(f"size_pct must be in (0, 1], got {self.size_pct}")
        if self.price <= 0:
            raise ValueError(f"price must be positive, got {self.price}")


@dataclass
class Signal:
    """Trading signal from a playbook.
    
    Contains all information needed to execute and manage a trade.
    
    Attributes:
        playbook_name: Name of playbook generating signal
        direction: LONG or SHORT
        entry_price: Intended entry price
        initial_stop: Initial stop loss price
        profit_targets: List of profit target levels
        strength: Signal strength (0-1)
        regime_alignment: How well signal fits current regime (0-1)
        confidence: Overall confidence score (0-1)
        metadata: Additional context (setup details, indicators, etc.)
        timestamp: When signal was generated
    """
    playbook_name: str
    direction: Direction
    entry_price: float
    initial_stop: float
    profit_targets: List[ProfitTarget]
    strength: float
    regime_alignment: float
    confidence: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: Optional[pd.Timestamp] = None
    
    def __post_init__(self):
        """Validate signal."""
        if not 0 <= self.strength <= 1:
            raise ValueError(f"strength must be in [0, 1], got {self.strength}")
        if not 0 <= self.regime_alignment <= 1:
            raise ValueError(f"regime_alignment must be in [0, 1], got {self.regime_alignment}")
        if not 0 <= self.confidence <= 1:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")
        
        # Validate stop is on correct side of entry
        if self.direction == Direction.LONG:
            if self.initial_stop >= self.entry_price:
                raise ValueError(
                    f"LONG stop ({self.initial_stop}) must be below entry ({self.entry_price})"
                )
        else:
            if self.initial_stop <= self.entry_price:
                raise ValueError(
                    f"SHORT stop ({self.initial_stop}) must be above entry ({self.entry_price})"
                )
    
    @property
    def initial_risk(self) -> float:
        """Calculate initial risk (entry to stop) in points."""
        return abs(self.entry_price - self.initial_stop)
    
    @property
    def signal_strength_level(self) -> SignalStrength:
        """Classify signal strength."""
        if self.strength >= 0.7:
            return SignalStrength.STRONG
        elif self.strength >= 0.4:
            return SignalStrength.MODERATE
        else:
            return SignalStrength.WEAK
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert signal to dictionary."""
        return {
            'playbook_name': self.playbook_name,
            'direction': self.direction.value,
            'entry_price': self.entry_price,
            'initial_stop': self.initial_stop,
            'initial_risk': self.initial_risk,
            'profit_targets': [
                {
                    'price': pt.price,
                    'size_pct': pt.size_pct,
                    'label': pt.label,
                    'r_multiple': pt.r_multiple
                }
                for pt in self.profit_targets
            ],
            'strength': self.strength,
            'signal_strength_level': self.signal_strength_level.value,
            'regime_alignment': self.regime_alignment,
            'confidence': self.confidence,
            'metadata': self.metadata,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
        }


@dataclass
class PlaybookStats:
    """Statistics for a playbook's historical performance.
    
    Used for signal arbitration and position sizing decisions.
    """
    playbook_name: str
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_r: float = 0.0
    avg_win_r: float = 0.0
    avg_loss_r: float = 0.0
    win_rate: float = 0.0
    expectancy: float = 0.0
    sharpe_ratio: float = 0.0
    max_consecutive_losses: int = 0
    avg_bars_in_trade: float = 0.0
    
    def update(self, r_multiple: float, bars_in_trade: int, is_win: bool):
        """Update statistics with new trade result."""
        self.total_trades += 1
        self.total_r += r_multiple
        
        if is_win:
            self.winning_trades += 1
            # Update average win
            old_total = self.avg_win_r * (self.winning_trades - 1)
            self.avg_win_r = (old_total + r_multiple) / self.winning_trades
        else:
            self.losing_trades += 1
            # Update average loss
            old_total = self.avg_loss_r * (self.losing_trades - 1)
            self.avg_loss_r = (old_total + r_multiple) / self.losing_trades
        
        # Update win rate
        self.win_rate = self.winning_trades / self.total_trades
        
        # Update expectancy
        self.expectancy = (
            self.win_rate * self.avg_win_r + 
            (1 - self.win_rate) * self.avg_loss_r
        )
        
        # Update average bars
        old_total = self.avg_bars_in_trade * (self.total_trades - 1)
        self.avg_bars_in_trade = (old_total + bars_in_trade) / self.total_trades


class Playbook(ABC):
    """Abstract base class for all trading playbooks.
    
    Each playbook implements a specific trading strategy that works well
    in certain market regimes. Playbooks are responsible for:
    
    1. Signal generation (entry conditions)
    2. Initial stop placement
    3. Profit target calculation
    4. Stop management (three-phase logic)
    5. Salvage/early exit conditions
    
    Example:
        >>> class MyPlaybook(Playbook):
        ...     @property
        ...     def name(self):
        ...         return "My Strategy"
        ...     
        ...     def check_entry(self, market_data, regime, features):
        ...         # Implement entry logic
        ...         if conditions_met:
        ...             return Signal(...)
        ...         return None
    """
    
    def __init__(self):
        """Initialize playbook."""
        self.stats = PlaybookStats(playbook_name=self.name)
        self.enabled = True
        self.config: Dict[str, Any] = {}
        
    @property
    @abstractmethod
    def name(self) -> str:
        """Playbook name."""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Brief description of the playbook strategy."""
        pass
    
    @property
    @abstractmethod
    def preferred_regimes(self) -> List[str]:
        """Regimes where this playbook performs best.
        
        Returns:
            List of regime names: ["TREND", "RANGE", "VOLATILE", "TRANSITIONAL"]
        """
        pass
    
    @property
    @abstractmethod
    def playbook_type(self) -> str:
        """Type of playbook: "MEAN_REVERSION", "MOMENTUM", "BREAKOUT", "FADE" """
        pass
    
    @abstractmethod
    def check_entry(
        self,
        bars: pd.DataFrame,
        current_bar: pd.Series,
        regime: str,
        features: Dict[str, float],
        open_positions: List[Any],
        mbp10_snapshot: Optional[Dict] = None,
    ) -> Optional[Signal]:
        """Check if entry conditions are met.
        
        Args:
            bars: Historical bars for context
            current_bar: Most recent bar
            regime: Current market regime
            features: Current feature values
            open_positions: List of currently open positions
            mbp10_snapshot: MBP-10 order book snapshot (optional)
            
        Returns:
            Signal if conditions met, None otherwise
        """
        pass
    
    @abstractmethod
    def update_stops(
        self,
        position: Any,
        bars: pd.DataFrame,
        current_bar: pd.Series,
        mfe: float,
        mae: float,
    ) -> float:
        """Update stop loss based on three-phase logic.
        
        Args:
            position: Current position object
            bars: Historical bars
            current_bar: Current bar
            mfe: Maximum Favorable Excursion (in R)
            mae: Maximum Adverse Excursion (in R)
            
        Returns:
            New stop price
        """
        pass
    
    @abstractmethod
    def check_salvage(
        self,
        position: Any,
        bars: pd.DataFrame,
        current_bar: pd.Series,
        mfe: float,
        mae: float,
        bars_in_trade: int,
    ) -> bool:
        """Check if position should be salvaged (early exit).
        
        Args:
            position: Current position
            bars: Historical bars
            current_bar: Current bar
            mfe: Maximum Favorable Excursion (in R)
            mae: Maximum Adverse Excursion (in R)
            bars_in_trade: Bars since entry
            
        Returns:
            True if position should be exited early
        """
        pass
    
    def get_regime_alignment(self, regime: str) -> float:
        """Calculate how well current regime aligns with playbook.
        
        Args:
            regime: Current regime name
            
        Returns:
            Alignment score (0-1)
        """
        if regime in self.preferred_regimes:
            return 1.0
        elif regime == "TRANSITIONAL":
            return 0.5
        else:
            return 0.2
    
    def calculate_position_size(
        self,
        signal: Signal,
        account_size: float,
        risk_per_trade: float,
    ) -> int:
        """Calculate position size based on risk.
        
        Args:
            signal: Trading signal
            account_size: Account size in dollars
            risk_per_trade: Risk per trade as fraction (e.g., 0.01 = 1%)
            
        Returns:
            Number of contracts
        """
        risk_dollars = account_size * risk_per_trade
        risk_per_contract = signal.initial_risk * self._get_point_value()
        
        if risk_per_contract <= 0:
            logger.warning(f"Invalid risk per contract: {risk_per_contract}")
            return 0
        
        size = int(risk_dollars / risk_per_contract)
        
        return max(size, 1)  # At least 1 contract
    
    def _get_point_value(self) -> float:
        """Get point value for the instrument.
        
        Override in subclass if needed. Default assumes ES ($50 per point).
        
        Returns:
            Dollar value per point
        """
        return 50.0  # ES default
    
    def update_stats(self, r_multiple: float, bars_in_trade: int):
        """Update playbook statistics with trade result.
        
        Args:
            r_multiple: R-multiple achieved (positive = win, negative = loss)
            bars_in_trade: Number of bars in trade
        """
        is_win = r_multiple > 0
        self.stats.update(r_multiple, bars_in_trade, is_win)
        
        logger.debug(
            f"{self.name}: Updated stats - "
            f"Win rate: {self.stats.win_rate:.1%}, "
            f"Expectancy: {self.stats.expectancy:.3f}R, "
            f"Trades: {self.stats.total_trades}"
        )
    
    def get_summary(self) -> str:
        """Get playbook summary with statistics.
        
        Returns:
            Formatted summary string
        """
        lines = [
            "="*60,
            f"PLAYBOOK: {self.name}",
            "="*60,
            f"Description: {self.description}",
            f"Type: {self.playbook_type}",
            f"Preferred Regimes: {', '.join(self.preferred_regimes)}",
            f"Enabled: {self.enabled}",
            "",
            "PERFORMANCE STATISTICS:",
            f"  Total Trades: {self.stats.total_trades}",
            f"  Win Rate: {self.stats.win_rate:.1%}",
            f"  Avg Win: {self.stats.avg_win_r:.3f}R",
            f"  Avg Loss: {self.stats.avg_loss_r:.3f}R",
            f"  Expectancy: {self.stats.expectancy:.3f}R",
            f"  Total R: {self.stats.total_r:.2f}R",
            f"  Avg Bars: {self.stats.avg_bars_in_trade:.1f}",
            "="*60,
        ]
        
        return "\n".join(lines)
    
    def __repr__(self) -> str:
        """String representation."""
        return f"<{self.__class__.__name__}(name='{self.name}', enabled={self.enabled})>"


class PlaybookRegistry:
    """Registry for managing multiple playbooks.
    
    Provides centralized management of all playbooks in the system.
    
    Example:
        >>> registry = PlaybookRegistry()
        >>> registry.register(IBFadePlaybook())
        >>> registry.register(VWAPMagnetPlaybook())
        >>> 
        >>> # Get playbooks for current regime
        >>> active_playbooks = registry.get_playbooks_for_regime("RANGE")
    """
    
    def __init__(self):
        """Initialize registry."""
        self.playbooks: Dict[str, Playbook] = {}
        
    def register(self, playbook: Playbook):
        """Register a playbook.
        
        Args:
            playbook: Playbook instance to register
        """
        if playbook.name in self.playbooks:
            logger.warning(f"Overwriting existing playbook: {playbook.name}")
        
        self.playbooks[playbook.name] = playbook
        logger.info(f"Registered playbook: {playbook.name}")
    
    def unregister(self, name: str):
        """Unregister a playbook.
        
        Args:
            name: Playbook name
        """
        if name in self.playbooks:
            del self.playbooks[name]
            logger.info(f"Unregistered playbook: {name}")
        else:
            logger.warning(f"Playbook not found: {name}")
    
    def get(self, name: str) -> Optional[Playbook]:
        """Get playbook by name.
        
        Args:
            name: Playbook name
            
        Returns:
            Playbook instance or None
        """
        return self.playbooks.get(name)
    
    def get_all(self) -> List[Playbook]:
        """Get all registered playbooks.
        
        Returns:
            List of all playbooks
        """
        return list(self.playbooks.values())
    
    def get_enabled(self) -> List[Playbook]:
        """Get all enabled playbooks.
        
        Returns:
            List of enabled playbooks
        """
        return [pb for pb in self.playbooks.values() if pb.enabled]
    
    def get_playbooks_for_regime(self, regime: str) -> List[Playbook]:
        """Get playbooks suitable for current regime.
        
        Args:
            regime: Current regime name
            
        Returns:
            List of playbooks that prefer this regime
        """
        suitable = []
        for playbook in self.get_enabled():
            if regime in playbook.preferred_regimes:
                suitable.append(playbook)
        
        return suitable
    
    def get_by_type(self, playbook_type: str) -> List[Playbook]:
        """Get playbooks by type.
        
        Args:
            playbook_type: "MEAN_REVERSION", "MOMENTUM", etc.
            
        Returns:
            List of playbooks of that type
        """
        return [
            pb for pb in self.get_enabled()
            if pb.playbook_type == playbook_type
        ]
    
    def disable_all(self):
        """Disable all playbooks."""
        for playbook in self.playbooks.values():
            playbook.enabled = False
        logger.info("Disabled all playbooks")
    
    def enable_all(self):
        """Enable all playbooks."""
        for playbook in self.playbooks.values():
            playbook.enabled = True
        logger.info("Enabled all playbooks")
    
    def get_summary(self) -> str:
        """Get summary of all playbooks.
        
        Returns:
            Formatted summary string
        """
        lines = [
            "="*60,
            "PLAYBOOK REGISTRY",
            "="*60,
            f"Total Playbooks: {len(self.playbooks)}",
            f"Enabled: {len(self.get_enabled())}",
            "",
        ]
        
        for playbook in self.playbooks.values():
            status = "✓" if playbook.enabled else "✗"
            lines.append(
                f"[{status}] {playbook.name:30s} "
                f"({playbook.playbook_type}, "
                f"Trades: {playbook.stats.total_trades}, "
                f"E: {playbook.stats.expectancy:.3f}R)"
            )
        
        lines.append("="*60)
        
        return "\n".join(lines)

