"""Trade lifecycle manager.

Handles position entry, stop/target placement, partial fills, breakeven shifts,
and exit logic.
"""

from datetime import datetime
from typing import Optional, Tuple

import pandas as pd
from loguru import logger

from ..config import TradeConfig, StopMode, ORBConfig
from ..features.or_builder import OpeningRange
from ..features.indicators import compute_atr
from ..signals.detector import BreakoutSignal, Direction
from .position import Position, PositionState, ExitReason


class TradeManager:
    """Manages trade lifecycle from entry to exit.

    Responsibilities:
    - Create positions from breakout signals
    - Place stops and targets
    - Monitor for fills (stops, targets, partials)
    - Move stops to breakeven
    - Update MAE/MFE
    """

    def __init__(
        self,
        trade_config: TradeConfig,
        orb_config: ORBConfig,
    ) -> None:
        """Initialize trade manager.

        Args:
            trade_config: Trade configuration.
            orb_config: OR configuration (for ATR calculations).
        """
        self.config = trade_config
        self.orb_config = orb_config

    def create_position(
        self,
        signal: BreakoutSignal,
        opening_range: OpeningRange,
    ) -> Position:
        """Create new position from breakout signal.

        Args:
            signal: Breakout signal.
            opening_range: Opening range for stop placement.

        Returns:
            Position instance with stops and targets set.
        """
        # Create position
        position = Position(
            symbol=opening_range.symbol,
            direction=signal.direction,
            entry_time=signal.timestamp,
            entry_price=signal.trigger_price,
            quantity=1.0,  # Simplified - would use sizing logic in production
            or_high=opening_range.or_high,
            or_low=opening_range.or_low,
            or_width=opening_range.or_width,
            or_valid=opening_range.is_valid,
            confluence_score_long=signal.confluence_score.long_score,
            confluence_score_short=signal.confluence_score.short_score,
            factor_signals={
                name: {
                    "long": sig.long_signal,
                    "short": sig.short_signal,
                    "value": sig.value,
                }
                for name, sig in signal.confluence_score.factor_signals.items()
            },
        )

        # Place initial stop
        self._place_stop(position, opening_range, signal)

        # Place targets
        self._place_targets(position)

        logger.info(
            f"Created {position.direction.value} position for {position.symbol} "
            f"at {position.entry_price}, stop={position.initial_stop}, "
            f"R={position.initial_risk:.4f}"
        )

        return position

    def update_position(
        self,
        position: Position,
        df: pd.DataFrame,
        bar_idx: int,
    ) -> None:
        """Update position for current bar (check stops/targets, update MAE/MFE).

        Args:
            position: Position to update.
            df: DataFrame with bar data.
            bar_idx: Current bar index.
        """
        if not position.is_open:
            return

        bar = df.iloc[bar_idx]
        bar_time = df.index[bar_idx]

        # Update excursion tracking
        position.update_excursion(bar["high"])
        position.update_excursion(bar["low"])

        # Check for stop hit
        if self._check_stop_hit(position, bar):
            exit_price = position.current_stop
            position.close_position(bar_time, exit_price, ExitReason.STOP)
            logger.info(
                f"Position {position.trade_id} stopped out at {exit_price}, "
                f"R={position.realized_r:.2f}"
            )
            return

        # Check for target hits (in order: T1, T2, Runner)
        if self.config.partials:
            # Check T1
            if position.t1_quantity > 0 and self._check_target_hit(position, bar, position.target_1):
                position.add_partial_fill(
                    timestamp=bar_time,
                    price=position.target_1,
                    quantity=position.t1_quantity,
                    reason=ExitReason.TARGET_1,
                )
                position.t1_quantity = 0.0
                logger.info(f"Position {position.trade_id} hit T1 at {position.target_1}")

                # Move to breakeven after T1
                if not position.breakeven_moved:
                    self._move_to_breakeven(position)

            # Check T2
            if position.t2_quantity > 0 and self._check_target_hit(position, bar, position.target_2):
                position.add_partial_fill(
                    timestamp=bar_time,
                    price=position.target_2,
                    quantity=position.t2_quantity,
                    reason=ExitReason.TARGET_2,
                )
                position.t2_quantity = 0.0
                logger.info(f"Position {position.trade_id} hit T2 at {position.target_2}")

            # Check runner
            if (
                position.runner_quantity > 0
                and self._check_target_hit(position, bar, position.runner_target)
            ):
                position.add_partial_fill(
                    timestamp=bar_time,
                    price=position.runner_target,
                    quantity=position.runner_quantity,
                    reason=ExitReason.RUNNER,
                )
                position.runner_quantity = 0.0
                logger.info(f"Position {position.trade_id} hit runner at {position.runner_target}")

            # If all targets hit, close position
            if position.remaining_quantity <= 0:
                position.close_position(bar_time, position.runner_target, ExitReason.RUNNER)

        else:
            # Single target mode
            primary_target = position.target_1
            if self._check_target_hit(position, bar, primary_target):
                position.close_position(bar_time, primary_target, ExitReason.TARGET_1)
                logger.info(
                    f"Position {position.trade_id} hit target at {primary_target}, "
                    f"R={position.realized_r:.2f}"
                )
                return

        # Check for breakeven shift based on R achieved
        if not position.breakeven_moved:
            current_r = position.max_favorable_excursion
            if current_r >= self.config.move_be_at_r:
                self._move_to_breakeven(position)

    def _place_stop(
        self,
        position: Position,
        opening_range: OpeningRange,
        signal: BreakoutSignal,
    ) -> None:
        """Place initial stop based on stop mode.

        Args:
            position: Position to set stop for.
            opening_range: Opening range.
            signal: Breakout signal (for access to bar data if needed).
        """
        if self.config.stop_mode == StopMode.OR_OPPOSITE:
            # Opposite OR boundary + buffer
            if position.is_long:
                stop = opening_range.or_low - self.config.extra_stop_buffer
            else:
                stop = opening_range.or_high + self.config.extra_stop_buffer

        elif self.config.stop_mode == StopMode.SWING:
            # Swing pivot (simplified - would need pivot detection)
            # For now, fallback to OR_OPPOSITE
            logger.warning("SWING stop mode not fully implemented, using OR_OPPOSITE")
            if position.is_long:
                stop = opening_range.or_low - self.config.extra_stop_buffer
            else:
                stop = opening_range.or_high + self.config.extra_stop_buffer

        elif self.config.stop_mode == StopMode.ATR_CAPPED:
            # Structural stop but capped by ATR
            if position.is_long:
                structural_stop = opening_range.or_low - self.config.extra_stop_buffer
            else:
                structural_stop = opening_range.or_high + self.config.extra_stop_buffer

            # Apply ATR cap (would need DataFrame access for proper implementation)
            # For now, use structural stop directly
            stop = structural_stop

        else:
            raise ValueError(f"Unknown stop mode: {self.config.stop_mode}")

        position.initial_stop = stop
        position.current_stop = stop
        position.initial_risk = abs(position.entry_price - stop)

    def _place_targets(self, position: Position) -> None:
        """Place profit targets based on configuration.

        Args:
            position: Position to set targets for.
        """
        R = position.initial_risk

        if self.config.partials:
            # Multiple targets
            if position.is_long:
                position.target_1 = position.entry_price + self.config.t1_r * R
                position.target_2 = position.entry_price + self.config.t2_r * R
                position.runner_target = position.entry_price + self.config.runner_r * R
            else:
                position.target_1 = position.entry_price - self.config.t1_r * R
                position.target_2 = position.entry_price - self.config.t2_r * R
                position.runner_target = position.entry_price - self.config.runner_r * R

            # Allocate quantities
            position.t1_quantity = position.quantity * self.config.t1_pct
            position.t2_quantity = position.quantity * self.config.t2_pct
            position.runner_quantity = position.quantity - position.t1_quantity - position.t2_quantity

        else:
            # Single target
            if position.is_long:
                position.target_1 = position.entry_price + self.config.primary_r * R
            else:
                position.target_1 = position.entry_price - self.config.primary_r * R

    def _check_stop_hit(self, position: Position, bar: pd.Series) -> bool:
        """Check if stop was hit in the bar.

        Args:
            position: Position.
            bar: Bar data (Series).

        Returns:
            True if stop hit.
        """
        if position.is_long:
            return bar["low"] <= position.current_stop
        else:
            return bar["high"] >= position.current_stop

    def _check_target_hit(self, position: Position, bar: pd.Series, target: Optional[float]) -> bool:
        """Check if target was hit in the bar.

        Args:
            position: Position.
            bar: Bar data.
            target: Target price.

        Returns:
            True if target hit.
        """
        if target is None:
            return False

        if position.is_long:
            return bar["high"] >= target
        else:
            return bar["low"] <= target

    def _move_to_breakeven(self, position: Position) -> None:
        """Move stop to breakeven (+ buffer).

        Args:
            position: Position to adjust.
        """
        be_stop = position.entry_price

        # Add small buffer (in ticks/points)
        if position.is_long:
            be_stop += self.config.be_buffer
        else:
            be_stop -= self.config.be_buffer

        # Only move stop if it improves risk (don't move backwards)
        if position.is_long and be_stop > position.current_stop:
            position.current_stop = be_stop
            position.breakeven_moved = True
            logger.debug(f"Position {position.trade_id} stop moved to breakeven at {be_stop}")
        elif position.is_short and be_stop < position.current_stop:
            position.current_stop = be_stop
            position.breakeven_moved = True
            logger.debug(f"Position {position.trade_id} stop moved to breakeven at {be_stop}")
