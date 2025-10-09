"""Multi-Playbook Strategy Orchestrator.

Master class that integrates:
- Feature calculation
- Regime detection
- Multiple playbooks
- Signal arbitration
- Portfolio management
- Position management

This is the main entry point for the complete trading system.

Based on Dr. Hoffman's Elite Multi-Playbook Framework from 10_08_project_review.md
"""

from typing import List, Dict, Optional, Any
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger

from orb_confluence.features.advanced_features import AdvancedFeatures
from orb_confluence.strategy.regime_classifier import RegimeClassifier
from orb_confluence.strategy.playbook_base import Playbook, Signal, PlaybookRegistry
from orb_confluence.strategy.signal_arbitrator import SignalArbitrator, CrossEntropyMinimizer
from orb_confluence.strategy.portfolio_manager import PortfolioManager, PositionAllocation


@dataclass
class Position:
    """Active trading position.
    
    Attributes:
        playbook_name: Name of playbook that generated this position
        direction: LONG or SHORT
        entry_price: Entry price
        entry_time: Entry timestamp
        size: Position size in contracts
        initial_stop: Initial stop loss price
        current_stop: Current stop loss price (trails)
        profit_targets: List of profit targets
        initial_risk: Initial risk per contract (entry - stop)
        mfe: Maximum Favorable Excursion (R)
        mae: Maximum Adverse Excursion (R)
        bars_in_trade: Number of bars since entry
        metadata: Additional position data
    """
    playbook_name: str
    direction: Any  # Direction enum
    entry_price: float
    entry_time: Any  # Timestamp
    size: int
    initial_stop: float
    current_stop: float
    profit_targets: List[Any]
    initial_risk: float
    mfe: float = 0.0
    mae: float = 0.0
    bars_in_trade: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TradeResult:
    """Completed trade result.
    
    Attributes:
        playbook_name: Playbook that generated trade
        direction: Trade direction
        entry_price: Entry price
        exit_price: Exit price
        entry_time: Entry timestamp
        exit_time: Exit timestamp
        size: Position size
        r_multiple: R-multiple achieved
        pnl: Profit/loss in dollars
        bars_in_trade: Duration in bars
        exit_reason: Reason for exit
        mfe: Maximum favorable excursion
        mae: Maximum adverse excursion
        metadata: Additional trade data
    """
    playbook_name: str
    direction: Any
    entry_price: float
    exit_price: float
    entry_time: Any
    exit_time: Any
    size: int
    r_multiple: float
    pnl: float
    bars_in_trade: int
    exit_reason: str
    mfe: float
    mae: float
    metadata: Dict[str, Any]


class MultiPlaybookStrategy:
    """Master strategy orchestrator for multi-playbook system.
    
    This is the main class that brings together all components:
    - Feature calculation (AdvancedFeatures)
    - Regime detection (RegimeClassifier)
    - Multiple playbooks (via PlaybookRegistry)
    - Signal arbitration (SignalArbitrator)
    - Portfolio management (PortfolioManager)
    - Position lifecycle management
    
    Example:
        >>> strategy = MultiPlaybookStrategy(
        ...     playbooks=[ib_fade, vwap_magnet, momentum, opening_drive],
        ...     account_size=100000,
        ...     base_risk=0.01,
        ... )
        >>> 
        >>> # On each bar
        >>> actions = strategy.on_bar(
        ...     current_bar=bar,
        ...     bars_1m=historical_1m,
        ...     bars_daily=historical_daily,
        ... )
        >>> 
        >>> for action in actions:
        ...     execute_action(action)
    """
    
    def __init__(
        self,
        playbooks: List[Playbook],
        account_size: float,
        base_risk: float = 0.01,
        max_simultaneous_positions: int = 3,
        target_volatility: float = 0.01,
        max_portfolio_heat: float = 0.05,
        enable_signal_arbitration: bool = True,
        enable_correlation_weighting: bool = True,
        point_value: float = 50.0,
    ):
        """Initialize multi-playbook strategy.
        
        Args:
            playbooks: List of playbook instances
            account_size: Account size in dollars
            base_risk: Base risk per trade (default: 1%)
            max_simultaneous_positions: Max concurrent positions (default: 3)
            target_volatility: Target portfolio volatility (default: 1%)
            max_portfolio_heat: Max total portfolio risk (default: 5%)
            enable_signal_arbitration: Use signal arbitrator (default: True)
            enable_correlation_weighting: Use correlation weighting (default: True)
            point_value: Dollar value per point (default: 50 for ES)
        """
        # Core components
        self.playbooks = playbooks
        self.account_size = account_size
        self.base_risk = base_risk
        self.max_simultaneous_positions = max_simultaneous_positions
        self.point_value = point_value
        
        # Initialize subsystems
        self.features = AdvancedFeatures()
        self.regime_classifier = RegimeClassifier(n_components=4)
        self.registry = PlaybookRegistry()
        self.arbitrator = SignalArbitrator(max_simultaneous_signals=1)
        self.cross_entropy_minimizer = CrossEntropyMinimizer()
        self.portfolio_manager = PortfolioManager(
            target_volatility=target_volatility,
            max_portfolio_heat=max_portfolio_heat,
            point_value=point_value,
        )
        
        # Configuration
        self.enable_signal_arbitration = enable_signal_arbitration
        self.enable_correlation_weighting = enable_correlation_weighting
        
        # Register playbooks
        for playbook in playbooks:
            self.registry.register(playbook)
        
        # State
        self.open_positions: List[Position] = []
        self.closed_trades: List[TradeResult] = []
        self.current_regime: Optional[str] = None
        self.current_features: Dict[str, float] = {}
        self.regime_fitted = False
        
        # Performance tracking
        self.total_trades = 0
        self.winning_trades = 0
        self.total_r = 0.0
        
        logger.info(
            f"Initialized MultiPlaybookStrategy with {len(playbooks)} playbooks, "
            f"account_size=${account_size:,.0f}, base_risk={base_risk:.1%}"
        )
    
    def fit_regime_classifier(self, historical_bars: pd.DataFrame):
        """Fit regime classifier on historical data.
        
        Must be called before strategy can detect regimes.
        
        Args:
            historical_bars: Historical 1m bars for training
        """
        logger.info(f"Fitting regime classifier on {len(historical_bars)} bars...")
        
        # Calculate features for training
        feature_rows = []
        
        # Use rolling windows to create training samples
        window_size = 60  # 1 hour
        for i in range(window_size, len(historical_bars), 30):
            window = historical_bars.iloc[i-window_size:i]
            
            # Calculate features
            features = self.features.calculate_all_features(
                bars_1m=window,
                bars_daily=None,  # Would need daily bars
                bars_1s=None,
            )
            
            # Convert to list
            feature_vector = [
                features.get('volatility_term_structure', 0),
                features.get('overnight_auction_imbalance', 0),
                features.get('rotation_entropy', 0),
                features.get('relative_volume_intensity', 0),
                features.get('directional_commitment', 0),
                features.get('microstructure_pressure', 0),
                features.get('intraday_yield_curve', 0),
                features.get('composite_liquidity_score', 0),
            ]
            
            feature_rows.append(feature_vector)
        
        # Fit classifier - convert to DataFrame with proper column names
        feature_names = [
            'volatility_term_structure',
            'overnight_auction_imbalance',
            'rotation_entropy',
            'relative_volume_intensity',
            'directional_commitment',
            'microstructure_pressure',
            'intraday_yield_curve',
            'composite_liquidity_score',
        ]
        X = pd.DataFrame(feature_rows, columns=feature_names)
        logger.info(f"Created feature matrix: {X.shape[0]} samples, {X.shape[1]} features")
        
        self.regime_classifier.fit(X)
        self.regime_fitted = True
        
        logger.info("Regime classifier fitted successfully")
    
    def on_bar(
        self,
        current_bar: pd.Series,
        bars_1m: pd.DataFrame,
        bars_daily: Optional[pd.DataFrame] = None,
        bars_1s: Optional[pd.DataFrame] = None,
        overnight_bars: Optional[pd.DataFrame] = None,
    ) -> List[Dict[str, Any]]:
        """Process a new bar and generate trading actions.
        
        This is the main method called on each bar update.
        
        Args:
            current_bar: Current 1m bar
            bars_1m: Historical 1m bars (including current)
            bars_daily: Historical daily bars (optional)
            bars_1s: Historical 1s bars (optional)
            overnight_bars: Overnight session bars (optional)
            
        Returns:
            List of actions to execute: [
                {'action': 'ENTER', 'signal': Signal, 'allocation': PositionAllocation},
                {'action': 'EXIT', 'position_id': int, 'reason': str, 'price': float},
                {'action': 'UPDATE_STOP', 'position_id': int, 'new_stop': float},
                ...
            ]
        """
        actions = []
        
        # Step 1: Calculate features
        self.current_features = self.features.calculate_all_features(
            bars_1m=bars_1m,
            bars_daily=bars_daily,
            bars_1s=bars_1s,
            overnight_bars=overnight_bars,
        )
        
        # Step 2: Detect regime
        if self.regime_fitted:
            feature_vector = [
                self.current_features.get('volatility_term_structure', 0),
                self.current_features.get('overnight_auction_imbalance', 0),
                self.current_features.get('rotation_entropy', 0),
                self.current_features.get('relative_volume_intensity', 0),
                self.current_features.get('directional_commitment', 0),
                self.current_features.get('microstructure_pressure', 0),
                self.current_features.get('intraday_yield_curve', 0),
                self.current_features.get('composite_liquidity_score', 0),
            ]
            X = np.array([feature_vector])
            self.current_regime = self.regime_classifier.predict(X)[0]
        else:
            self.current_regime = "UNKNOWN"
        
        # Step 3: Update existing positions
        position_actions = self._manage_positions(current_bar, bars_1m)
        actions.extend(position_actions)
        
        # Step 4: Generate new signals (if not at position limit)
        if len(self.open_positions) < self.max_simultaneous_positions:
            signal_actions = self._generate_signals(current_bar, bars_1m)
            actions.extend(signal_actions)
        
        return actions
    
    def _manage_positions(
        self,
        current_bar: pd.Series,
        bars: pd.DataFrame,
    ) -> List[Dict[str, Any]]:
        """Manage existing positions (stops, salvage, targets).
        
        Args:
            current_bar: Current bar
            bars: Historical bars
            
        Returns:
            List of position management actions
        """
        actions = []
        current_price = current_bar['close']
        
        for i, position in enumerate(list(self.open_positions)):
            # Update MFE/MAE using high/low for accurate intra-bar tracking
            position.bars_in_trade += 1
            
            # For LONG: high is most favorable, low is most adverse
            # For SHORT: low is most favorable, high is most adverse
            if position.direction.value == 'LONG':
                current_r_favorable = self._calculate_current_r(position, current_bar['high'])
                current_r_adverse = self._calculate_current_r(position, current_bar['low'])
            else:  # SHORT
                current_r_favorable = self._calculate_current_r(position, current_bar['low'])
                current_r_adverse = self._calculate_current_r(position, current_bar['high'])
            
            position.mfe = max(position.mfe, current_r_favorable)
            position.mae = min(position.mae, current_r_adverse)
            
            # Get playbook
            playbook = self.registry.get(position.playbook_name)
            if not playbook:
                continue
            
            # Check stop hit
            stop_hit = self._check_stop_hit(position, current_bar)
            if stop_hit:
                # Update MFE/MAE with the actual exit price to ensure consistency
                exit_r = self._calculate_current_r(position, position.current_stop)
                position.mfe = max(position.mfe, exit_r)
                position.mae = min(position.mae, exit_r)
                
                actions.append({
                    'action': 'EXIT',
                    'position_id': i,
                    'reason': 'STOP',
                    'price': position.current_stop,
                })
                # Get timestamp from current_bar (ensure it's a proper datetime)
                exit_time = current_bar.get('timestamp')
                if exit_time is not None and not isinstance(exit_time, datetime):
                    exit_time = pd.Timestamp(exit_time)
                self._close_position(position, position.current_stop, 'STOP', exit_time)
                continue
            
            # Check salvage
            should_salvage = playbook.check_salvage(
                position=position,
                bars=bars,
                current_bar=current_bar,
                mfe=position.mfe,
                mae=position.mae,
                bars_in_trade=position.bars_in_trade,
            )
            
            if should_salvage:
                actions.append({
                    'action': 'EXIT',
                    'position_id': i,
                    'reason': 'SALVAGE',
                    'price': current_price,
                })
                # Get timestamp from current_bar (ensure it's a proper datetime)
                exit_time = current_bar.get('timestamp')
                if exit_time is not None and not isinstance(exit_time, datetime):
                    exit_time = pd.Timestamp(exit_time)
                self._close_position(position, current_price, 'SALVAGE', exit_time)
                continue
            
            # Update stops
            new_stop = playbook.update_stops(
                position=position,
                bars=bars,
                current_bar=current_bar,
                mfe=position.mfe,
                mae=position.mae,
            )
            
            if new_stop != position.current_stop:
                position.current_stop = new_stop
                actions.append({
                    'action': 'UPDATE_STOP',
                    'position_id': i,
                    'new_stop': new_stop,
                })
            
            # Check profit targets
            target_hit = self._check_target_hit(position, current_bar)
            if target_hit:
                target_price, target_pct = target_hit
                partial_size = int(position.size * target_pct)
                
                # Update MFE/MAE with the actual target price to ensure consistency
                target_r = self._calculate_current_r(position, target_price)
                position.mfe = max(position.mfe, target_r)
                position.mae = min(position.mae, target_r)
                
                actions.append({
                    'action': 'PARTIAL_EXIT',
                    'position_id': i,
                    'size': partial_size,
                    'price': target_price,
                    'reason': 'TARGET',
                })
                
                # Update position size
                position.size -= partial_size
                
                if position.size <= 0:
                    # Get timestamp from current_bar (ensure it's a proper datetime)
                    exit_time = current_bar.get('timestamp')
                    if exit_time is not None and not isinstance(exit_time, datetime):
                        exit_time = pd.Timestamp(exit_time)
                    self._close_position(position, target_price, 'TARGET', exit_time)
        
        return actions
    
    def _generate_signals(
        self,
        current_bar: pd.Series,
        bars: pd.DataFrame,
    ) -> List[Dict[str, Any]]:
        """Generate new trading signals.
        
        Args:
            current_bar: Current bar
            bars: Historical bars
            
        Returns:
            List of entry actions
        """
        actions = []
        
        # Get playbooks for current regime
        regime_playbooks = self.registry.get_playbooks_for_regime(self.current_regime)
        
        if not regime_playbooks:
            return actions
        
        # Generate signals from each playbook
        signals = []
        for playbook in regime_playbooks:
            signal = playbook.check_entry(
                bars=bars,
                current_bar=current_bar,
                regime=self.current_regime,
                features=self.current_features,
                open_positions=self.open_positions,
            )
            
            if signal:
                signals.append(signal)
        
        if not signals:
            return actions
        
        logger.info(f"Generated {len(signals)} signals")
        
        # Apply cross-entropy filter for mean reversion signals
        signals = self.cross_entropy_minimizer.filter_redundant_signals(signals)
        
        if not signals:
            return actions
        
        # Arbitrate if multiple signals
        if len(signals) > 1 and self.enable_signal_arbitration:
            current_hour = current_bar.get('timestamp', datetime.now()).hour
            decision = self.arbitrator.arbitrate(
                signals=signals,
                current_regime=self.current_regime,
                current_hour=current_hour,
                open_positions=self.open_positions,
            )
            
            if decision:
                signals = [decision.selected_signal]
            else:
                signals = []
        
        # Size and execute signals
        for signal in signals:
            # Calculate position size
            allocation = self.portfolio_manager.calculate_position_size(
                signal=signal,
                account_size=self.account_size,
                base_risk=self.base_risk,
                open_positions=self.open_positions,
                regime_clarity=signal.regime_alignment,
                realized_volatility=self.portfolio_manager.get_realized_volatility(),
            )
            
            if allocation.final_size > 0:
                actions.append({
                    'action': 'ENTER',
                    'signal': signal,
                    'allocation': allocation,
                })
                
                # Create position
                self._open_position(signal, allocation)
        
        return actions
    
    def _open_position(self, signal: Signal, allocation: PositionAllocation):
        """Open a new position.
        
        Args:
            signal: Trading signal
            allocation: Position allocation
        """
        position = Position(
            playbook_name=signal.playbook_name,
            direction=signal.direction,
            entry_price=signal.entry_price,
            entry_time=signal.timestamp,
            size=allocation.final_size,
            initial_stop=signal.initial_stop,
            current_stop=signal.initial_stop,
            profit_targets=signal.profit_targets,
            initial_risk=signal.initial_risk,
            metadata=signal.metadata.copy(),
        )
        
        self.open_positions.append(position)
        
        logger.info(
            f"Opened {signal.direction.value} position: "
            f"{signal.playbook_name}, size={allocation.final_size}, "
            f"entry={signal.entry_price:.2f}, stop={signal.initial_stop:.2f}"
        )
    
    def _close_position(
        self,
        position: Position,
        exit_price: float,
        exit_reason: str,
        exit_time: Any = None,
    ):
        """Close a position and record trade.
        
        Args:
            position: Position to close
            exit_price: Exit price
            exit_reason: Reason for exit
            exit_time: Exit timestamp (defaults to now if not provided)
        """
        # Calculate R-multiple
        r_multiple = self._calculate_current_r(position, exit_price)
        
        # Improve exit reason labeling
        # If labeled as STOP but R is positive, it's actually a trailing stop
        if exit_reason == 'STOP':
            if r_multiple > 0.05:  # More than 0.05R profit
                exit_reason = 'TRAIL'  # Trailing stop that locked in profit
            elif abs(r_multiple) < 0.05:  # Close to breakeven
                exit_reason = 'BREAKEVEN'
        
        # Calculate P&L
        if position.direction.value == 'LONG':
            pnl = (exit_price - position.entry_price) * position.size * self.point_value
        else:
            pnl = (position.entry_price - exit_price) * position.size * self.point_value
        
        # Use provided exit_time or default to now
        if exit_time is None:
            exit_time = datetime.now()
        elif hasattr(exit_time, 'to_pydatetime'):
            # Convert pandas Timestamp to datetime
            exit_time = exit_time.to_pydatetime()
        elif isinstance(exit_time, (int, float)):
            # Convert numeric timestamp to datetime (nanoseconds since epoch)
            exit_time = pd.Timestamp(exit_time, unit='ns').to_pydatetime()
        
        # Create trade result
        trade = TradeResult(
            playbook_name=position.playbook_name,
            direction=position.direction,
            entry_price=position.entry_price,
            exit_price=exit_price,
            entry_time=position.entry_time,
            exit_time=exit_time,
            size=position.size,
            r_multiple=r_multiple,
            pnl=pnl,
            bars_in_trade=position.bars_in_trade,
            exit_reason=exit_reason,
            mfe=position.mfe,
            mae=position.mae,
            metadata=position.metadata.copy(),
        )
        
        self.closed_trades.append(trade)
        
        # Update stats
        self.total_trades += 1
        if r_multiple > 0:
            self.winning_trades += 1
        self.total_r += r_multiple
        
        # Remove from open positions
        if position in self.open_positions:
            self.open_positions.remove(position)
        
        logger.info(
            f"Closed {position.playbook_name}: "
            f"{r_multiple:.2f}R, PNL=${pnl:,.0f}, "
            f"reason={exit_reason}, bars={position.bars_in_trade}"
        )
    
    def _check_stop_hit(self, position: Position, current_bar: pd.Series) -> bool:
        """Check if stop was hit.
        
        Args:
            position: Position
            current_bar: Current bar
            
        Returns:
            True if stop hit
        """
        if position.direction.value == 'LONG':
            return current_bar['low'] <= position.current_stop
        else:
            return current_bar['high'] >= position.current_stop
    
    def _check_target_hit(self, position: Position, current_bar: pd.Series) -> Optional[tuple]:
        """Check if profit target was hit.
        
        Args:
            position: Position
            current_bar: Current bar
            
        Returns:
            Tuple of (target_price, target_size_pct) if hit, None otherwise
        """
        if not position.profit_targets:
            return None
        
        # Check first target
        target = position.profit_targets[0]
        
        if position.direction.value == 'LONG':
            if current_bar['high'] >= target.price:
                return (target.price, target.size_pct)
        else:
            if current_bar['low'] <= target.price:
                return (target.price, target.size_pct)
        
        return None
    
    def _calculate_current_r(self, position: Position, current_price: float) -> float:
        """Calculate current R-multiple for position.
        
        Args:
            position: Position
            current_price: Current price
            
        Returns:
            Current R-multiple
        """
        if position.initial_risk <= 0:
            return 0.0
        
        if position.direction.value == 'LONG':
            profit = current_price - position.entry_price
        else:
            profit = position.entry_price - current_price
        
        return profit / position.initial_risk
    
    def get_stats(self) -> Dict[str, Any]:
        """Get strategy statistics.
        
        Returns:
            Dictionary with comprehensive stats
        """
        if self.total_trades == 0:
            win_rate = 0.0
            avg_r = 0.0
        else:
            win_rate = self.winning_trades / self.total_trades
            avg_r = self.total_r / self.total_trades
        
        # Playbook breakdown
        playbook_trades = {}
        for trade in self.closed_trades:
            pb = trade.playbook_name
            if pb not in playbook_trades:
                playbook_trades[pb] = {'count': 0, 'total_r': 0.0}
            playbook_trades[pb]['count'] += 1
            playbook_trades[pb]['total_r'] += trade.r_multiple
        
        return {
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'win_rate': win_rate,
            'total_r': self.total_r,
            'average_r': avg_r,
            'open_positions': len(self.open_positions),
            'current_regime': self.current_regime,
            'playbook_breakdown': playbook_trades,
            'arbitrator_stats': self.arbitrator.get_stats(),
            'portfolio_stats': self.portfolio_manager.get_stats(),
        }
    
    def reset(self):
        """Reset strategy state (useful for testing)."""
        self.open_positions = []
        self.closed_trades = []
        self.total_trades = 0
        self.winning_trades = 0
        self.total_r = 0.0
        self.portfolio_manager.reset_heat()
        logger.info("Reset strategy state")

