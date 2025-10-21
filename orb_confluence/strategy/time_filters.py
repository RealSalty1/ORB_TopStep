"""Time-of-Day Trading Filters

Phase 2 Enhancement #2: Addresses time-dependent performance problem.

Key Findings from Phase 1 Analysis:
- Morning (9-11 ET): 0.145R avg - HIGHLY PROFITABLE
- Midday (11-14 ET): 0.013R avg - Break-even
- Afternoon (14-16 ET): 0.021R avg - Weak
- Other times: -0.067R avg - LOSING (61.7% of trades!)

Solution:
- Focus 100% capital on morning prime time
- Reduce size and increase quality threshold for other times
- Skip or minimize trading outside core hours

Expected Impact:
- Filter out 40-50% of losing trades
- Estimated improvement: +0.05R to +0.08R per trade
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Tuple
from loguru import logger


class TimeWindow(str, Enum):
    """Time window classifications."""
    PRIME = "prime"         # 9-11 ET: Best performance
    GOOD = "good"           # 14-16 ET: Decent performance
    AVOID = "avoid"         # All other times: Poor performance
    OFF_HOURS = "off_hours" # Outside market hours


@dataclass
class TimeFilterParams:
    """Parameters for time-based filtering.
    
    Attributes:
        window: Time window classification
        position_multiplier: Position size multiplier (0.0-1.0)
        quality_threshold: Minimum quality score required (0-100)
        skip_trading: Whether to skip trading entirely
        description: Human-readable description
    """
    window: TimeWindow
    position_multiplier: float
    quality_threshold: int
    skip_trading: bool
    description: str


class TimeOfDayFilter:
    """Filter trades based on time of day performance.
    
    Based on Phase 1 analysis of July 2025 showing dramatic time-dependent
    performance differences. Morning sessions (9-11 ET) were highly profitable
    (0.145R avg) while 61.7% of trades outside core hours lost money.
    
    Time Windows:
    - PRIME (9-11 ET): Full size, lower quality threshold
    - GOOD (14-16 ET): Reduced size, higher quality threshold
    - AVOID (other hours): Minimal size, very high quality threshold
    - OFF_HOURS: No trading
    
    Example:
        >>> filter = TimeOfDayFilter()
        >>> params = filter.get_time_params(current_hour=10)  # 10 AM ET
        >>> print(params.window)  # TimeWindow.PRIME
        >>> print(params.position_multiplier)  # 1.0 (full size)
        
        >>> params = filter.get_time_params(current_hour=19)  # 7 PM ET
        >>> print(params.skip_trading)  # True (outside market hours)
    """
    
    def __init__(
        self,
        prime_start: int = 9,           # 9 AM ET
        prime_end: int = 11,            # 11 AM ET
        good_start: int = 14,           # 2 PM ET
        good_end: int = 16,             # 4 PM ET
        market_open: int = 9,           # Market opens 9:30 AM, but use 9 for safety
        market_close: int = 16,         # Market closes 4:00 PM
        prime_quality_threshold: int = 50,      # B-grade minimum
        good_quality_threshold: int = 65,       # B+ grade minimum
        avoid_quality_threshold: int = 80,      # A-grade minimum
        prime_position_multiplier: float = 1.0,    # Full size
        good_position_multiplier: float = 0.7,     # 70% size
        avoid_position_multiplier: float = 0.3,    # 30% size
        enable_avoid_window: bool = True,          # Trade during avoid hours?
    ):
        """Initialize time-of-day filter.
        
        Args:
            prime_start: Prime window start hour (ET, 24-hour format)
            prime_end: Prime window end hour (ET, 24-hour format)
            good_start: Good window start hour (ET, 24-hour format)
            good_end: Good window end hour (ET, 24-hour format)
            market_open: Market open hour (ET)
            market_close: Market close hour (ET)
            prime_quality_threshold: Min quality score for prime window
            good_quality_threshold: Min quality score for good window
            avoid_quality_threshold: Min quality score for avoid window
            prime_position_multiplier: Position size multiplier for prime
            good_position_multiplier: Position size multiplier for good
            avoid_position_multiplier: Position size multiplier for avoid
            enable_avoid_window: Whether to allow trading during avoid window
        """
        self.prime_hours = (prime_start, prime_end)
        self.good_hours = (good_start, good_end)
        self.market_hours = (market_open, market_close)
        
        self.prime_quality_threshold = prime_quality_threshold
        self.good_quality_threshold = good_quality_threshold
        self.avoid_quality_threshold = avoid_quality_threshold
        
        self.prime_position_multiplier = prime_position_multiplier
        self.good_position_multiplier = good_position_multiplier
        self.avoid_position_multiplier = avoid_position_multiplier
        
        self.enable_avoid_window = enable_avoid_window
        
        logger.info(
            f"TimeOfDayFilter initialized: "
            f"PRIME={prime_start}-{prime_end}ET, "
            f"GOOD={good_start}-{good_end}ET, "
            f"avoid_enabled={enable_avoid_window}"
        )
    
    def get_time_params(self, timestamp: datetime) -> TimeFilterParams:
        """Get time-based parameters for given timestamp.
        
        Args:
            timestamp: Current timestamp (should be in ET timezone)
            
        Returns:
            TimeFilterParams with appropriate settings
        """
        hour = timestamp.hour
        
        # Check if outside market hours
        if hour < self.market_hours[0] or hour >= self.market_hours[1]:
            return TimeFilterParams(
                window=TimeWindow.OFF_HOURS,
                position_multiplier=0.0,
                quality_threshold=100,
                skip_trading=True,
                description=f"Outside market hours ({hour}:00 ET)"
            )
        
        # Check prime window (9-11 ET)
        if self.prime_hours[0] <= hour < self.prime_hours[1]:
            return TimeFilterParams(
                window=TimeWindow.PRIME,
                position_multiplier=self.prime_position_multiplier,
                quality_threshold=self.prime_quality_threshold,
                skip_trading=False,
                description=f"Prime time ({hour}:00 ET) - Best performance (0.145R avg)"
            )
        
        # Check good window (14-16 ET)
        if self.good_hours[0] <= hour < self.good_hours[1]:
            return TimeFilterParams(
                window=TimeWindow.GOOD,
                position_multiplier=self.good_position_multiplier,
                quality_threshold=self.good_quality_threshold,
                skip_trading=False,
                description=f"Good time ({hour}:00 ET) - Decent performance (0.021R avg)"
            )
        
        # Avoid window (all other market hours)
        if self.enable_avoid_window:
            return TimeFilterParams(
                window=TimeWindow.AVOID,
                position_multiplier=self.avoid_position_multiplier,
                quality_threshold=self.avoid_quality_threshold,
                skip_trading=False,
                description=f"Avoid time ({hour}:00 ET) - Poor performance (-0.067R avg)"
            )
        else:
            # Skip trading entirely during avoid window
            return TimeFilterParams(
                window=TimeWindow.AVOID,
                position_multiplier=0.0,
                quality_threshold=100,
                skip_trading=True,
                description=f"Avoid time ({hour}:00 ET) - Trading disabled"
            )
    
    def should_trade(
        self,
        timestamp: datetime,
        setup_quality: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """Determine if should trade at given time with given quality.
        
        Args:
            timestamp: Current timestamp
            setup_quality: Quality score of setup (0-100), None to skip check
            
        Returns:
            Tuple of (should_trade: bool, reason: str)
        """
        params = self.get_time_params(timestamp)
        
        # Check if trading is disabled for this window
        if params.skip_trading:
            return False, params.description
        
        # If no quality score provided, allow (quality check done elsewhere)
        if setup_quality is None:
            return True, params.description
        
        # Check quality threshold
        if setup_quality < params.quality_threshold:
            return False, (
                f"Quality {setup_quality} below {params.window.value} threshold "
                f"({params.quality_threshold})"
            )
        
        return True, params.description
    
    def adjust_position_size(
        self,
        base_size: float,
        timestamp: datetime,
    ) -> float:
        """Adjust position size based on time of day.
        
        Args:
            base_size: Base position size
            timestamp: Current timestamp
            
        Returns:
            Adjusted position size
        """
        params = self.get_time_params(timestamp)
        adjusted = base_size * params.position_multiplier
        
        if adjusted != base_size:
            logger.debug(
                f"Position size adjusted for {params.window.value}: "
                f"{base_size:.0f} → {adjusted:.0f} "
                f"(multiplier: {params.position_multiplier:.0%})"
            )
        
        return adjusted
    
    def get_statistics(self) -> dict:
        """Get filter statistics summary.
        
        Returns:
            Dictionary with filter configuration
        """
        return {
            'prime_hours': f"{self.prime_hours[0]}-{self.prime_hours[1]} ET",
            'good_hours': f"{self.good_hours[0]}-{self.good_hours[1]} ET",
            'prime_quality_threshold': self.prime_quality_threshold,
            'good_quality_threshold': self.good_quality_threshold,
            'avoid_quality_threshold': self.avoid_quality_threshold,
            'prime_position_multiplier': self.prime_position_multiplier,
            'good_position_multiplier': self.good_position_multiplier,
            'avoid_position_multiplier': self.avoid_position_multiplier,
            'avoid_window_enabled': self.enable_avoid_window,
        }


class AggressiveTimeFilter(TimeOfDayFilter):
    """Aggressive time filter that ONLY trades morning prime time.
    
    This is the most conservative approach based on Phase 1 findings.
    Only allows trading 9-11 AM ET when performance is consistently strong.
    
    Use this for:
    - Initial testing to maximize safety
    - Low confidence market conditions
    - During drawdowns
    """
    
    def __init__(self):
        """Initialize aggressive filter (prime time only)."""
        super().__init__(
            prime_start=9,
            prime_end=11,
            good_start=14,
            good_end=16,
            prime_quality_threshold=50,      # B-grade minimum
            good_quality_threshold=100,      # Effectively disabled
            avoid_quality_threshold=100,     # Effectively disabled
            prime_position_multiplier=1.0,
            good_position_multiplier=0.0,    # No trading
            avoid_position_multiplier=0.0,   # No trading
            enable_avoid_window=False,
        )
        
        logger.info("AggressiveTimeFilter initialized: PRIME TIME ONLY (9-11 ET)")


class BalancedTimeFilter(TimeOfDayFilter):
    """Balanced time filter with all windows enabled.
    
    This is the recommended default based on Phase 1 findings.
    Allows trading throughout the day but adjusts size and quality requirements.
    
    Use this for:
    - Normal market conditions
    - After initial validation
    - Production deployment
    """
    
    def __init__(self):
        """Initialize balanced filter (all windows with adjustments)."""
        super().__init__(
            prime_start=9,
            prime_end=11,
            good_start=14,
            good_end=16,
            prime_quality_threshold=50,      # B-grade minimum
            good_quality_threshold=65,       # B+ grade minimum
            avoid_quality_threshold=80,      # A-grade minimum
            prime_position_multiplier=1.0,   # Full size
            good_position_multiplier=0.7,    # 70% size
            avoid_position_multiplier=0.3,   # 30% size
            enable_avoid_window=True,
        )
        
        logger.info(
            "BalancedTimeFilter initialized: "
            "PRIME (100%), GOOD (70%), AVOID (30%)"
        )





