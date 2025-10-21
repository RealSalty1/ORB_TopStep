"""Enhanced Multi-Playbook Strategy with Phase 2 Integration.

This wraps MultiPlaybookStrategy and integrates all Phase 2 enhancements:
- TwoPhaseTradeManager for advanced stop management
- TimeFilter for time-of-day filtering
- EntryQualityScorer for setup quality filtering
- TopStepRiskManager for Combine compliance

This allows us to use the full production strategy with Phase 2 enhancements
without modifying the core MultiPlaybookStrategy class.
"""

from typing import List, Dict, Optional, Any
import pandas as pd
from datetime import datetime
from loguru import logger

from orb_confluence.strategy.multi_playbook_strategy import MultiPlaybookStrategy, Position
from orb_confluence.strategy.playbook_base import Playbook, Signal
from orb_confluence.strategy.two_phase_trade_manager import TwoPhaseTradeManager
from orb_confluence.strategy.time_filters import TimeOfDayFilter, TimeFilterParams
from orb_confluence.strategy.entry_quality import EntryQualityScorer, QualityScore
from orb_confluence.risk.topstep_manager import TopStepRiskManager
from orb_confluence.strategy.trade_state import ActiveTrade


class EnhancedMultiPlaybookStrategy(MultiPlaybookStrategy):
    """Enhanced strategy with Phase 2 improvements integrated.
    
    This extends MultiPlaybookStrategy to add:
    - 2-Phase Stop Logic (BE @ 0.3R, Trail @ 0.5R)
    - Time-of-Day Filters (Prime/Good/Avoid)
    - Entry Quality Scoring (C-grade minimum)
    - TopStep Risk Management
    
    Example:
        >>> strategy = EnhancedMultiPlaybookStrategy(
        ...     playbooks=[opening_drive, ib_fade, momentum],
        ...     account_size=100000,
        ...     base_risk=0.01,
        ...     enable_phase2=True,  # Enable all Phase 2 enhancements
        ... )
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
        mbp10_loader: Optional[Any] = None,
        # Phase 2 Enhancement Parameters
        enable_phase2: bool = False,
        trade_manager: Optional[TwoPhaseTradeManager] = None,
        time_filter: Optional[TimeOfDayFilter] = None,
        quality_scorer: Optional[EntryQualityScorer] = None,
        risk_manager: Optional[TopStepRiskManager] = None,
    ):
        """Initialize enhanced strategy.
        
        Args:
            playbooks: List of playbook instances
            account_size: Account size in dollars
            base_risk: Base risk per trade (e.g., 0.01 = 1%)
            max_simultaneous_positions: Max number of concurrent positions
            target_volatility: Target portfolio volatility
            max_portfolio_heat: Max portfolio heat (total risk)
            enable_signal_arbitration: Enable signal arbitration
            enable_correlation_weighting: Enable correlation weighting
            point_value: Point value for futures (e.g., 50 for ES)
            mbp10_loader: MBP-10 data loader
            enable_phase2: Enable all Phase 2 enhancements (if True, creates default components)
            trade_manager: Custom TwoPhaseTradeManager (optional)
            time_filter: Custom TimeOfDayFilter (optional)
            quality_scorer: Custom EntryQualityScorer (optional)
            risk_manager: Custom TopStepRiskManager (optional)
        """
        # Initialize base strategy
        super().__init__(
            playbooks=playbooks,
            account_size=account_size,
            base_risk=base_risk,
            max_simultaneous_positions=max_simultaneous_positions,
            target_volatility=target_volatility,
            max_portfolio_heat=max_portfolio_heat,
            enable_signal_arbitration=enable_signal_arbitration,
            enable_correlation_weighting=enable_correlation_weighting,
            point_value=point_value,
            mbp10_loader=mbp10_loader,
        )
        
        # Phase 2 Components
        self.enable_phase2 = enable_phase2
        
        if enable_phase2:
            # Create default Phase 2 components if not provided
            self.trade_manager = trade_manager or TwoPhaseTradeManager(
                breakeven_threshold_r=0.3,
                trailing_start_r=0.5,
                trail_distance_r=0.3,
            )
            
            # Import here to avoid circular imports
            from orb_confluence.strategy.time_filters import BalancedTimeFilter
            from orb_confluence.strategy.entry_quality import AggressiveQualityScorer
            
            self.time_filter = time_filter or BalancedTimeFilter()
            self.quality_scorer = quality_scorer or AggressiveQualityScorer()
            self.risk_manager = risk_manager or TopStepRiskManager(
                account_size=account_size,
                is_combine=True,
            )
            
            logger.info("✅ Phase 2 Enhancements ENABLED")
            logger.info(f"  - 2-Phase Trade Manager: {type(self.trade_manager).__name__}")
            logger.info(f"  - Time Filter: {type(self.time_filter).__name__}")
            logger.info(f"  - Quality Scorer: {type(self.quality_scorer).__name__}")
            logger.info(f"  - Risk Manager: TopStep Combine Mode")
        else:
            self.trade_manager = None
            self.time_filter = None
            self.quality_scorer = None
            self.risk_manager = None
            logger.info("Phase 2 Enhancements DISABLED (using baseline strategy)")
        
        # Map positions to ActiveTrade objects for TwoPhaseTradeManager
        self.active_trades: Dict[int, ActiveTrade] = {}
    
    def _generate_signals(
        self,
        current_bar: pd.Series,
        bars: pd.DataFrame,
        mbp10_snapshot: Optional[Dict] = None,
    ) -> List[Dict[str, Any]]:
        """Generate signals with Phase 2 filtering.
        
        Overrides base method to add:
        - Entry quality scoring and filtering
        - Time-of-day filtering and position sizing adjustment
        """
        # Get base signals from parent class
        actions = super()._generate_signals(current_bar, bars, mbp10_snapshot)
        
        if not self.enable_phase2:
            return actions
        
        # Apply Phase 2 filters
        filtered_actions = []
        
        for action in actions:
            if action['action'] != 'ENTER':
                filtered_actions.append(action)
                continue
            
            signal = action['signal']
            timestamp = signal.timestamp
            
            # Get time filter parameters
            filter_params = self.time_filter.get_time_params(timestamp)
            
            # Check if we should skip trading at this time
            if filter_params.skip_trading:
                logger.debug(f"SKIP: {signal.playbook_name} - {filter_params.description}")
                continue
            
            # Score the setup quality
            setup_dict = signal.metadata.copy()
            setup_dict.update({
                'entry_price': signal.entry_price,
                'stop_price': signal.initial_stop,
                'direction': signal.direction.value,
            })
            
            quality_score = self.quality_scorer.calculate_quality(
                setup=setup_dict,
                market_state=None,  # Could pass regime info here
                mbp_data=None,  # Could pass MBP data here
                timestamp=timestamp,
            )
            
            # Filter by quality threshold
            if quality_score.total < filter_params.quality_threshold:
                logger.debug(
                    f"REJECT: {signal.playbook_name} - Quality {quality_score.total} "
                    f"< threshold {filter_params.quality_threshold} ({filter_params.description})"
                )
                continue
            
            # Adjust position size based on time of day
            allocation = action['allocation']
            original_size = allocation.final_size
            adjusted_size = int(original_size * filter_params.position_multiplier)
            
            # Apply TopStep risk management circuit breaker
            if self.risk_manager:
                risk_status = self.risk_manager.can_trade()
                if not risk_status.can_trade:
                    logger.warning(
                        f"HALT: {signal.playbook_name} - TopStep limit: {', '.join(risk_status.reasons)}"
                    )
                    continue
                
                adjusted_size = self.risk_manager.get_position_size_limit(adjusted_size)
            
            # Update allocation
            allocation.final_size = adjusted_size
            
            if adjusted_size <= 0:
                logger.debug(f"SKIP: {signal.playbook_name} - Position size reduced to 0")
                continue
            
            logger.info(
                f"ACCEPT: {signal.playbook_name} - Quality {quality_score.grade} ({quality_score.total}), "
                f"Size {original_size} → {adjusted_size} ({filter_params.description})"
            )
            
            filtered_actions.append(action)
        
        return filtered_actions
    
    def _update_positions(
        self,
        current_bar: pd.Series,
        bars: pd.DataFrame,
        mbp10_snapshot: Optional[Dict] = None,
    ) -> List[Dict[str, Any]]:
        """Update positions with Phase 2 stop management.
        
        Overrides base method to use TwoPhaseTradeManager for stop logic.
        """
        if not self.enable_phase2:
            # Use base implementation
            return super()._update_positions(current_bar, bars, mbp10_snapshot)
        
        actions = []
        positions_to_remove = []
        
        for i, position in enumerate(self.open_positions):
            # Convert Position to ActiveTrade if not already mapped
            if i not in self.active_trades:
                self.active_trades[i] = self._position_to_active_trade(position)
            
            active_trade = self.active_trades[i]
            
            # Update R extremes (MFE/MAE)
            current_price = current_bar['high'] if position.direction.value == 'LONG' else current_bar['low']
            active_trade.update_r_extremes(current_price)
            
            # Use TwoPhaseTradeManager to update the trade
            trade_update = self.trade_manager.update(active_trade, current_bar)
            
            # Sync back to Position object
            position.current_stop = active_trade.stop_price_current
            position.mfe = active_trade.max_favorable_r
            position.mae = active_trade.max_adverse_r
            position.bars_in_trade += 1
            
            # Check if trade was closed by TwoPhaseTradeManager
            if trade_update.closed:
                exit_price = active_trade.exit_price or current_price
                exit_reason = active_trade.exit_reason or 'unknown'
                
                actions.append({
                    'action': 'EXIT',
                    'position_id': i,
                    'reason': exit_reason.upper(),
                    'price': exit_price,
                })
                
                exit_time = current_bar.get('timestamp')
                if exit_time is not None and not isinstance(exit_time, datetime):
                    exit_time = pd.Timestamp(exit_time)
                
                self._close_position(position, exit_price, exit_reason.upper(), exit_time)
                positions_to_remove.append(i)
                
                # Update TopStep risk manager with PNL
                if self.risk_manager:
                    r_multiple = active_trade.realized_r or 0.0
                    pnl_dollars = r_multiple * position.initial_risk * position.size * self.point_value
                    self.risk_manager.update_equity(pnl_dollars, exit_time or datetime.now())
                
                continue
            
            # Check stop updates
            if any(event.value == 'BREAKEVEN_MOVE' for event in trade_update.events):
                actions.append({
                    'action': 'UPDATE_STOP',
                    'position_id': i,
                    'new_stop': position.current_stop,
                    'reason': 'BREAKEVEN',
                })
            
            # Still use base class logic for salvage and order flow exits
            # (TwoPhaseTradeManager handles stop/target/trailing, but not playbook-specific exits)
            playbook = self.registry.get_playbook(position.playbook_name)
            
            if playbook:
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
                    
                    exit_time = current_bar.get('timestamp')
                    if exit_time is not None and not isinstance(exit_time, datetime):
                        exit_time = pd.Timestamp(exit_time)
                    
                    self._close_position(position, current_price, 'SALVAGE', exit_time)
                    positions_to_remove.append(i)
                    continue
                
                # Check order flow exit
                order_flow_exit_reason = playbook.check_order_flow_exit(
                    position=position,
                    mbp10_snapshot=mbp10_snapshot,
                    mfe=position.mfe,
                )
                
                if order_flow_exit_reason:
                    actions.append({
                        'action': 'EXIT',
                        'position_id': i,
                        'reason': order_flow_exit_reason,
                        'price': current_price,
                    })
                    
                    exit_time = current_bar.get('timestamp')
                    if exit_time is not None and not isinstance(exit_time, datetime):
                        exit_time = pd.Timestamp(exit_time)
                    
                    self._close_position(position, current_price, order_flow_exit_reason, exit_time)
                    positions_to_remove.append(i)
                    continue
        
        # Clean up removed positions from active_trades map
        for pos_id in sorted(positions_to_remove, reverse=True):
            if pos_id in self.active_trades:
                del self.active_trades[pos_id]
        
        return actions
    
    def _position_to_active_trade(self, position: Position) -> ActiveTrade:
        """Convert a Position to an ActiveTrade for TwoPhaseTradeManager.
        
        Args:
            position: Position object from MultiPlaybookStrategy
            
        Returns:
            ActiveTrade object for TwoPhaseTradeManager
        """
        from orb_confluence.strategy.playbook_base import Direction
        
        # Generate a unique trade ID
        trade_id = f"trade_{len(self.active_trades) + 1}"
        
        return ActiveTrade(
            trade_id=trade_id,
            direction=position.direction.value.lower(),  # 'long' or 'short'
            entry_price=position.entry_price,
            entry_timestamp=position.entry_time,
            stop_price_initial=position.initial_stop,
            stop_price_current=position.current_stop,
            target_prices=[],  # TwoPhaseTradeManager doesn't use explicit targets
            initial_risk=position.initial_risk,
            position_size=position.size,
        )
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get comprehensive performance metrics including Phase 2 statistics.
        
        Returns:
            Dict with all performance metrics
        """
        base_metrics = super().get_performance_metrics()
        
        if not self.enable_phase2 or not self.risk_manager:
            return base_metrics
        
        # Add TopStep risk metrics
        phase2_metrics = {
            'phase2_enabled': True,
            'topstep_compliance': {
                'current_equity': self.risk_manager.current_equity,
                'peak_equity': self.risk_manager.peak_equity,
                'daily_pnl': self.risk_manager.daily_pnl,
                'weekly_pnl': self.risk_manager.weekly_pnl,
                'trading_halted': (
                    self.risk_manager.trading_halted_daily or
                    self.risk_manager.trading_halted_weekly or
                    self.risk_manager.trading_halted_drawdown
                ),
                'limit_violations': {
                    'daily': self.risk_manager.trading_halted_daily,
                    'weekly': self.risk_manager.trading_halted_weekly,
                    'drawdown': self.risk_manager.trading_halted_drawdown,
                }
            }
        }
        
        return {**base_metrics, **phase2_metrics}


# Convenience function to create enhanced strategy with defaults
def create_enhanced_strategy(
    playbooks: List[Playbook],
    account_size: float = 100000,
    base_risk: float = 0.01,
    enable_phase2: bool = True,
    **kwargs,
) -> EnhancedMultiPlaybookStrategy:
    """Create an enhanced strategy with sensible defaults.
    
    Args:
        playbooks: List of playbook instances
        account_size: Account size in dollars
        base_risk: Base risk per trade
        enable_phase2: Enable Phase 2 enhancements
        **kwargs: Additional arguments passed to EnhancedMultiPlaybookStrategy
        
    Returns:
        Configured EnhancedMultiPlaybookStrategy instance
    """
    return EnhancedMultiPlaybookStrategy(
        playbooks=playbooks,
        account_size=account_size,
        base_risk=base_risk,
        enable_phase2=enable_phase2,
        **kwargs,
    )

