"""Risk management: stop placement and target calculation.

Handles stop loss calculation using various modes and target
construction with partials support.
"""

from typing import List, Optional, Tuple

from loguru import logger

from ..features.opening_range import ORState


def compute_stop(
    signal_direction: str,
    entry_price: float,
    or_state: ORState,
    stop_mode: str = 'or_opposite',
    extra_buffer: float = 0.0,
    atr_cap_mult: Optional[float] = None,
    atr_value: Optional[float] = None,
    swing_high: Optional[float] = None,
    swing_low: Optional[float] = None,
) -> float:
    """Compute stop loss price.
    
    Args:
        signal_direction: 'long' or 'short'
        entry_price: Entry price
        or_state: Opening Range state
        stop_mode: Stop placement mode ('or_opposite', 'swing', 'atr_capped')
        extra_buffer: Extra buffer beyond structural stop
        atr_cap_mult: ATR cap multiplier (for atr_capped mode)
        atr_value: ATR value (for atr_capped mode)
        swing_high: Recent swing high (for swing mode)
        swing_low: Recent swing low (for swing mode)
        
    Returns:
        Stop price.
        
    Stop Modes:
        - or_opposite: Opposite side of OR + buffer
        - swing: Recent swing level + buffer
        - atr_capped: OR opposite, but capped at ATR multiple
        
    Examples:
        >>> # Long trade, OR opposite mode
        >>> or_state = ORState(..., high=100.5, low=100.0, ...)
        >>> stop = compute_stop('long', 100.6, or_state, 'or_opposite', 0.05)
        >>> assert stop == 99.95  # OR low - buffer
    """
    if signal_direction not in ['long', 'short']:
        raise ValueError(f"Invalid direction: {signal_direction}")
    
    if stop_mode == 'or_opposite':
        # Place stop at opposite side of OR with buffer
        if signal_direction == 'long':
            stop_price = or_state.low - extra_buffer
        else:  # short
            stop_price = or_state.high + extra_buffer
            
    elif stop_mode == 'swing':
        # Place stop beyond recent swing with buffer
        if signal_direction == 'long':
            if swing_low is None:
                raise ValueError("swing_low required for swing mode")
            stop_price = swing_low - extra_buffer
        else:  # short
            if swing_high is None:
                raise ValueError("swing_high required for swing mode")
            stop_price = swing_high + extra_buffer
            
    elif stop_mode == 'atr_capped':
        # OR opposite, but capped at ATR multiple
        if atr_value is None or atr_cap_mult is None:
            raise ValueError("atr_value and atr_cap_mult required for atr_capped mode")
        
        # Calculate OR opposite stop
        if signal_direction == 'long':
            or_stop = or_state.low - extra_buffer
        else:
            or_stop = or_state.high + extra_buffer
        
        # Calculate ATR-based max distance
        max_stop_distance = atr_cap_mult * atr_value
        
        # Cap the stop
        if signal_direction == 'long':
            atr_stop = entry_price - max_stop_distance
            stop_price = max(or_stop, atr_stop)  # Use closer stop
        else:  # short
            atr_stop = entry_price + max_stop_distance
            stop_price = min(or_stop, atr_stop)  # Use closer stop
            
    else:
        raise ValueError(f"Invalid stop_mode: {stop_mode}")
    
    logger.debug(
        f"{signal_direction.upper()} stop: {stop_price:.2f} (mode={stop_mode}, "
        f"entry={entry_price:.2f})"
    )
    
    return stop_price


def build_targets(
    entry_price: float,
    stop_price: float,
    direction: str,
    partials: bool = True,
    t1_r: float = 1.0,
    t1_pct: float = 0.5,
    t2_r: float = 1.5,
    t2_pct: float = 0.25,
    runner_r: float = 2.0,
    primary_r: float = 1.5,
) -> List[Tuple[float, float]]:
    """Build target list with partials.
    
    Args:
        entry_price: Entry price
        stop_price: Stop price
        direction: 'long' or 'short'
        partials: Use partial targets (if False, single target)
        t1_r: First target R-multiple
        t1_pct: First target size fraction
        t2_r: Second target R-multiple
        t2_pct: Second target size fraction
        runner_r: Runner target R-multiple
        primary_r: Primary target R (when partials=False)
        
    Returns:
        List of (price, size_fraction) tuples, sorted by R-multiple.
        
    Examples:
        >>> # Long trade with partials
        >>> targets = build_targets(100.0, 99.0, 'long', True, 1.0, 0.5, 1.5, 0.25, 2.0)
        >>> assert len(targets) == 3
        >>> assert targets[0] == (101.0, 0.5)  # T1: 1R, 50%
        >>> assert targets[1] == (101.5, 0.25)  # T2: 1.5R, 25%
        >>> assert targets[2] == (102.0, 0.25)  # Runner: 2R, 25%
    """
    initial_risk = abs(entry_price - stop_price)
    
    if initial_risk <= 0:
        raise ValueError(f"Invalid risk: entry={entry_price}, stop={stop_price}")
    
    targets = []
    
    if partials:
        # Calculate runner size (remainder after partials)
        runner_pct = 1.0 - t1_pct - t2_pct
        if runner_pct < 0:
            raise ValueError(f"Target percentages exceed 100%: {t1_pct + t2_pct}")
        
        # Build target list
        target_specs = [
            (t1_r, t1_pct),
            (t2_r, t2_pct),
            (runner_r, runner_pct),
        ]
        
        for r_mult, size_frac in target_specs:
            if size_frac > 0:  # Only include if non-zero
                if direction == 'long':
                    target_price = entry_price + (r_mult * initial_risk)
                else:  # short
                    target_price = entry_price - (r_mult * initial_risk)
                
                targets.append((target_price, size_frac))
    
    else:
        # Single target
        if direction == 'long':
            target_price = entry_price + (primary_r * initial_risk)
        else:
            target_price = entry_price - (primary_r * initial_risk)
        
        targets.append((target_price, 1.0))
    
    logger.debug(
        f"{direction.upper()} targets: {len(targets)} levels, "
        f"risk={initial_risk:.2f}"
    )
    
    return targets


def update_be_if_needed(
    entry_price: float,
    stop_price_current: float,
    direction: str,
    current_price: float,
    initial_risk: float,
    moved_to_breakeven: bool,
    threshold_r: float = 1.0,
    be_buffer: float = 0.0,
) -> Tuple[float, bool]:
    """Update stop to breakeven if threshold R reached.
    
    Args:
        entry_price: Entry price
        stop_price_current: Current stop price
        direction: 'long' or 'short'
        current_price: Current market price
        initial_risk: Initial risk (|entry - stop|)
        moved_to_breakeven: Whether already moved to BE
        threshold_r: R-multiple threshold to trigger BE move
        be_buffer: Buffer when moving to BE (e.g., 0.01 = 1 cent)
        
    Returns:
        Tuple of (new_stop_price, moved_to_be_flag).
        
    Examples:
        >>> # Long trade, price reaches 1R
        >>> new_stop, moved = update_be_if_needed(
        ...     entry_price=100.0,
        ...     stop_price_current=99.0,
        ...     direction='long',
        ...     current_price=101.0,  # 1R achieved
        ...     initial_risk=1.0,
        ...     moved_to_breakeven=False,
        ...     threshold_r=1.0,
        ...     be_buffer=0.05
        ... )
        >>> assert new_stop == 100.05  # Entry + buffer
        >>> assert moved is True
    """
    if moved_to_breakeven:
        # Already moved, return current stop
        return stop_price_current, True
    
    # Calculate current R
    if initial_risk <= 0:
        return stop_price_current, False
    
    if direction == 'long':
        current_r = (current_price - entry_price) / initial_risk
    else:  # short
        current_r = (entry_price - current_price) / initial_risk
    
    # Check if threshold reached
    if current_r >= threshold_r:
        # Move to breakeven + buffer
        if direction == 'long':
            new_stop = entry_price + be_buffer
        else:  # short
            new_stop = entry_price - be_buffer
        
        logger.info(
            f"Moving stop to breakeven: {stop_price_current:.2f} → {new_stop:.2f} "
            f"(current_r={current_r:.2f}, threshold={threshold_r:.2f})"
        )
        
        return new_stop, True
    
    # Threshold not reached
    return stop_price_current, False