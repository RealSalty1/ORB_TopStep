"""Portfolio Manager with correlation-weighted sizing and volatility targeting.

Manages position sizing across multiple playbooks considering:
- Volatility targeting (normalize by realized vol)
- Correlation-weighted exposure (reduce for correlated positions)
- Regime-conditional position limits
- Internal beta-neutralization

Based on Dr. Hoffman's 10_08_project_review.md Section 5.2
"""

from typing import List, Dict, Optional, Any
import numpy as np
import pandas as pd
from dataclasses import dataclass
from loguru import logger

from orb_confluence.strategy.playbook_base import Signal, Direction


@dataclass
class PositionAllocation:
    """Position size allocation for a signal.
    
    Attributes:
        signal: Original signal
        base_size: Base position size (contracts)
        adjusted_size: Size after correlation/volatility adjustments
        volatility_multiplier: Volatility adjustment factor
        correlation_multiplier: Correlation adjustment factor
        regime_multiplier: Regime clarity adjustment factor
        final_size: Final position size to execute
        metadata: Additional allocation details
    """
    signal: Signal
    base_size: int
    adjusted_size: float
    volatility_multiplier: float
    correlation_multiplier: float
    regime_multiplier: float
    final_size: int
    metadata: Dict[str, Any]


class PortfolioManager:
    """Manages portfolio-level risk and position sizing.
    
    Key Features:
    - Volatility targeting (normalize positions by realized vol)
    - Correlation-weighted sizing (reduce for correlated positions)
    - Regime-conditional limits (reduce size in unclear regimes)
    - Portfolio heat management (maximum total exposure)
    
    Example:
        >>> pm = PortfolioManager(
        ...     target_volatility=0.01,
        ...     max_portfolio_heat=0.05,
        ... )
        >>> allocation = pm.calculate_position_size(
        ...     signal=signal,
        ...     account_size=100000,
        ...     base_risk=0.01,
        ...     open_positions=positions,
        ...     regime_clarity=0.8,
        ... )
        >>> print(f"Execute {allocation.final_size} contracts")
    """
    
    def __init__(
        self,
        target_volatility: float = 0.01,
        max_portfolio_heat: float = 0.05,
        correlation_threshold: float = 0.7,
        min_regime_clarity: float = 0.5,
        point_value: float = 50.0,
    ):
        """Initialize portfolio manager.
        
        Args:
            target_volatility: Target portfolio volatility (default: 1%)
            max_portfolio_heat: Maximum total risk exposure (default: 5%)
            correlation_threshold: Threshold for correlation adjustment (default: 0.7)
            min_regime_clarity: Minimum regime clarity for full size (default: 0.5)
            point_value: Dollar value per point (default: 50 for ES)
        """
        self.target_volatility = target_volatility
        self.max_portfolio_heat = max_portfolio_heat
        self.correlation_threshold = correlation_threshold
        self.min_regime_clarity = min_regime_clarity
        self.point_value = point_value
        
        # Correlation matrix (playbook × playbook)
        self.correlation_matrix: Dict[str, Dict[str, float]] = {}
        
        # Realized volatility history
        self.volatility_history: List[float] = []
        
        # Current portfolio heat
        self.current_heat = 0.0
        
    def calculate_position_size(
        self,
        signal: Signal,
        account_size: float,
        base_risk: float,
        open_positions: Optional[List[Any]] = None,
        regime_clarity: float = 1.0,
        realized_volatility: Optional[float] = None,
    ) -> PositionAllocation:
        """Calculate position size with all adjustments.
        
        Args:
            signal: Trading signal
            account_size: Account size in dollars
            base_risk: Base risk per trade (e.g., 0.01 = 1%)
            open_positions: Currently open positions
            regime_clarity: Regime clarity score (0-1)
            realized_volatility: Recent realized volatility
            
        Returns:
            PositionAllocation with final size and breakdown
        """
        # Step 1: Calculate base position size (risk-based)
        base_size = self._calculate_base_size(
            signal, account_size, base_risk
        )
        
        # Step 2: Volatility adjustment
        vol_multiplier = self._calculate_volatility_multiplier(
            signal, realized_volatility
        )
        
        # Step 3: Correlation adjustment
        corr_multiplier = self._calculate_correlation_multiplier(
            signal, open_positions
        )
        
        # Step 4: Regime clarity adjustment
        regime_multiplier = self._calculate_regime_multiplier(
            regime_clarity
        )
        
        # Step 5: Apply all multipliers
        adjusted_size = base_size * vol_multiplier * corr_multiplier * regime_multiplier
        
        # Step 6: Check portfolio heat
        final_size = self._apply_heat_limit(
            adjusted_size, signal, account_size, open_positions
        )
        
        # Create allocation
        allocation = PositionAllocation(
            signal=signal,
            base_size=base_size,
            adjusted_size=adjusted_size,
            volatility_multiplier=vol_multiplier,
            correlation_multiplier=corr_multiplier,
            regime_multiplier=regime_multiplier,
            final_size=int(max(final_size, 1)),  # At least 1 contract
            metadata={
                'account_size': account_size,
                'base_risk': base_risk,
                'regime_clarity': regime_clarity,
                'portfolio_heat_before': self.current_heat,
            }
        )
        
        logger.info(
            f"Position sizing for {signal.playbook_name}: "
            f"base={base_size}, vol={vol_multiplier:.2f}x, "
            f"corr={corr_multiplier:.2f}x, regime={regime_multiplier:.2f}x, "
            f"final={allocation.final_size} contracts"
        )
        
        return allocation
    
    def _calculate_base_size(
        self,
        signal: Signal,
        account_size: float,
        base_risk: float,
    ) -> int:
        """Calculate base position size (risk-based).
        
        Args:
            signal: Trading signal
            account_size: Account size
            base_risk: Base risk percentage
            
        Returns:
            Base position size in contracts
        """
        risk_dollars = account_size * base_risk
        risk_per_contract = signal.initial_risk * self.point_value
        
        if risk_per_contract <= 0:
            logger.warning(f"Invalid risk per contract: {risk_per_contract}")
            return 1
        
        size = int(risk_dollars / risk_per_contract)
        
        return max(size, 1)
    
    def _calculate_volatility_multiplier(
        self,
        signal: Signal,
        realized_volatility: Optional[float],
    ) -> float:
        """Calculate volatility adjustment multiplier.
        
        Formula: multiplier = target_vol / (position_vol × instrument_vol)
        
        Lower volatility = larger position (to maintain target vol)
        Higher volatility = smaller position
        
        Args:
            signal: Trading signal
            realized_volatility: Recent realized volatility
            
        Returns:
            Volatility multiplier
        """
        if realized_volatility is None:
            # Use default if no realized vol available
            realized_volatility = 0.015  # 1.5% default
        
        # Position volatility multiplier (playbook-specific)
        playbook_vol_multipliers = {
            'Initial Balance Fade': 1.0,
            'VWAP Magnet': 0.9,
            'Momentum Continuation': 1.3,
            'Opening Drive Reversal': 0.8,
        }
        
        position_vol_mult = playbook_vol_multipliers.get(
            signal.playbook_name, 1.0
        )
        
        # Calculate multiplier
        combined_vol = realized_volatility * position_vol_mult
        
        if combined_vol <= 0:
            return 1.0
        
        multiplier = self.target_volatility / combined_vol
        
        # Limit multiplier range (0.5x to 2.0x)
        multiplier = np.clip(multiplier, 0.5, 2.0)
        
        return float(multiplier)
    
    def _calculate_correlation_multiplier(
        self,
        signal: Signal,
        open_positions: Optional[List[Any]],
    ) -> float:
        """Calculate correlation adjustment multiplier.
        
        Reduces size when adding correlated positions.
        
        Example: ES + NQ = reduce by 30-40% due to high correlation
        
        Args:
            signal: Trading signal
            open_positions: Open positions
            
        Returns:
            Correlation multiplier (0.6-1.0)
        """
        if not open_positions or len(open_positions) == 0:
            return 1.0  # No correlation if no positions
        
        # Get correlations with open positions
        correlations = []
        for pos in open_positions:
            if hasattr(pos, 'playbook_name'):
                corr = self._get_correlation(
                    signal.playbook_name, pos.playbook_name
                )
                if corr is not None:
                    correlations.append(abs(corr))  # Use absolute value
        
        if not correlations:
            return 1.0
        
        # Use maximum correlation (most restrictive)
        max_corr = max(correlations)
        
        # If below threshold, no adjustment
        if max_corr < self.correlation_threshold:
            return 1.0
        
        # Reduce size based on correlation
        # High correlation (0.9) → 0.6x size
        # Moderate correlation (0.7) → 0.9x size
        multiplier = 1.0 - ((max_corr - self.correlation_threshold) / (1.0 - self.correlation_threshold)) * 0.4
        
        return float(np.clip(multiplier, 0.6, 1.0))
    
    def _calculate_regime_multiplier(
        self,
        regime_clarity: float,
    ) -> float:
        """Calculate regime clarity adjustment.
        
        Reduces size in unclear/transitional regimes.
        
        Args:
            regime_clarity: Regime clarity score (0-1)
            
        Returns:
            Regime multiplier (0.6-1.0)
        """
        # Below minimum clarity, reduce significantly
        if regime_clarity < self.min_regime_clarity:
            return 0.6
        
        # Scale linearly from min_clarity to 1.0
        # At min_clarity (0.5): 0.6x
        # At perfect clarity (1.0): 1.0x
        multiplier = 0.6 + (regime_clarity - self.min_regime_clarity) / (1.0 - self.min_regime_clarity) * 0.4
        
        return float(np.clip(multiplier, 0.6, 1.0))
    
    def _apply_heat_limit(
        self,
        proposed_size: float,
        signal: Signal,
        account_size: float,
        open_positions: Optional[List[Any]],
    ) -> int:
        """Apply portfolio heat limit.
        
        Ensures total portfolio risk doesn't exceed max_portfolio_heat.
        
        Args:
            proposed_size: Proposed position size
            signal: Trading signal
            account_size: Account size
            open_positions: Open positions
            
        Returns:
            Final position size after heat limit
        """
        # Calculate risk of proposed position
        proposed_risk_dollars = proposed_size * signal.initial_risk * self.point_value
        proposed_risk_pct = proposed_risk_dollars / account_size
        
        # Calculate current portfolio risk
        current_risk = self._calculate_current_portfolio_risk(
            open_positions, account_size
        )
        
        # Total risk if we add this position
        total_risk = current_risk + proposed_risk_pct
        
        # If within limit, approve
        if total_risk <= self.max_portfolio_heat:
            self.current_heat = total_risk
            return int(proposed_size)
        
        # Otherwise, scale down to fit limit
        available_risk = self.max_portfolio_heat - current_risk
        
        if available_risk <= 0:
            logger.warning(
                f"Portfolio heat limit reached: {current_risk:.1%} "
                f"(max: {self.max_portfolio_heat:.1%})"
            )
            return 0
        
        # Scale size to fit available risk
        scale_factor = available_risk / proposed_risk_pct
        scaled_size = int(proposed_size * scale_factor)
        
        self.current_heat = current_risk + (available_risk * scale_factor)
        
        logger.info(
            f"Heat limit adjustment: {proposed_size:.1f} → {scaled_size} contracts "
            f"(heat: {current_risk:.1%} → {self.current_heat:.1%})"
        )
        
        return max(scaled_size, 1)
    
    def _calculate_current_portfolio_risk(
        self,
        open_positions: Optional[List[Any]],
        account_size: float,
    ) -> float:
        """Calculate current portfolio risk as percentage.
        
        Args:
            open_positions: Open positions
            account_size: Account size
            
        Returns:
            Total risk as percentage (0-1)
        """
        if not open_positions:
            return 0.0
        
        total_risk_dollars = 0.0
        for pos in open_positions:
            if hasattr(pos, 'initial_risk') and hasattr(pos, 'size'):
                position_risk = pos.size * pos.initial_risk * self.point_value
                total_risk_dollars += position_risk
        
        return total_risk_dollars / account_size
    
    def _get_correlation(
        self,
        playbook1: str,
        playbook2: str,
    ) -> Optional[float]:
        """Get correlation between two playbooks.
        
        Args:
            playbook1: First playbook name
            playbook2: Second playbook name
            
        Returns:
            Correlation (-1 to 1) or None if not available
        """
        # Check both directions
        if playbook1 in self.correlation_matrix:
            if playbook2 in self.correlation_matrix[playbook1]:
                return self.correlation_matrix[playbook1][playbook2]
        
        if playbook2 in self.correlation_matrix:
            if playbook1 in self.correlation_matrix[playbook2]:
                return self.correlation_matrix[playbook2][playbook1]
        
        # Default correlations (estimated)
        default_correlations = {
            ('Initial Balance Fade', 'VWAP Magnet'): 0.65,  # Both mean reversion
            ('Initial Balance Fade', 'Momentum Continuation'): 0.15,
            ('Initial Balance Fade', 'Opening Drive Reversal'): 0.35,
            ('VWAP Magnet', 'Momentum Continuation'): 0.10,
            ('VWAP Magnet', 'Opening Drive Reversal'): 0.40,
            ('Momentum Continuation', 'Opening Drive Reversal'): 0.05,
        }
        
        key1 = (playbook1, playbook2)
        key2 = (playbook2, playbook1)
        
        if key1 in default_correlations:
            return default_correlations[key1]
        elif key2 in default_correlations:
            return default_correlations[key2]
        
        return None
    
    def update_correlation_matrix(
        self,
        playbook1: str,
        playbook2: str,
        correlation: float,
    ):
        """Update correlation matrix with observed correlation.
        
        Args:
            playbook1: First playbook
            playbook2: Second playbook
            correlation: Correlation value (-1 to 1)
        """
        if playbook1 not in self.correlation_matrix:
            self.correlation_matrix[playbook1] = {}
        
        self.correlation_matrix[playbook1][playbook2] = correlation
        
        logger.debug(f"Updated correlation: {playbook1} × {playbook2} = {correlation:.2f}")
    
    def update_realized_volatility(self, daily_return: float):
        """Update realized volatility estimate.
        
        Args:
            daily_return: Daily return (e.g., 0.01 = 1%)
        """
        self.volatility_history.append(abs(daily_return))
        
        # Keep last 20 days
        if len(self.volatility_history) > 20:
            self.volatility_history.pop(0)
    
    def get_realized_volatility(self) -> float:
        """Get current realized volatility estimate.
        
        Returns:
            Realized volatility (annualized)
        """
        if len(self.volatility_history) < 5:
            return 0.015  # Default 1.5%
        
        # Calculate standard deviation of returns
        vol = np.std(self.volatility_history)
        
        # Annualize (252 trading days)
        annualized_vol = vol * np.sqrt(252)
        
        return float(annualized_vol)
    
    def calculate_beta_adjustment(
        self,
        signal: Signal,
        open_positions: List[Any],
    ) -> float:
        """Calculate internal beta-neutralization adjustment.
        
        If large ES position creates implicit NQ exposure, offset it.
        
        Args:
            signal: New signal
            open_positions: Open positions
            
        Returns:
            Beta adjustment factor (0.5-1.0)
        """
        # For simplicity, assume single instrument (ES)
        # In multi-instrument system, would calculate cross-instrument betas
        
        # If adding position in same direction as large existing position,
        # reduce size to prevent concentration
        
        if not open_positions:
            return 1.0
        
        same_direction_positions = [
            pos for pos in open_positions
            if hasattr(pos, 'direction') and pos.direction == signal.direction
        ]
        
        if len(same_direction_positions) >= 3:
            # Already have 3+ positions in same direction
            return 0.7  # Reduce to 70%
        elif len(same_direction_positions) == 2:
            return 0.85  # Reduce to 85%
        
        return 1.0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get portfolio manager statistics.
        
        Returns:
            Dictionary with stats
        """
        return {
            'current_portfolio_heat': self.current_heat,
            'max_portfolio_heat': self.max_portfolio_heat,
            'target_volatility': self.target_volatility,
            'realized_volatility': self.get_realized_volatility(),
            'correlation_matrix_size': sum(
                len(v) for v in self.correlation_matrix.values()
            ),
            'volatility_history_length': len(self.volatility_history),
        }
    
    def reset_heat(self):
        """Reset current portfolio heat (call at end of day or when all positions closed)."""
        self.current_heat = 0.0
        logger.debug("Reset portfolio heat to 0")

