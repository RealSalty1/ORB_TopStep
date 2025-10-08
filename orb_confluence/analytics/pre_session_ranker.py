"""Pre-session instrument ranking and scheduler.

Ranks instruments based on:
- Overnight range vs typical ADR
- Expected OR quality (historical)
- News risk (placeholder for future integration)
- Volatility regime alignment
- Recent strategy expectancy
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd
from datetime import datetime, date
from loguru import logger


@dataclass
class InstrumentScore:
    """Score for a single instrument."""
    symbol: str
    total_score: float
    
    # Component scores (0-1 normalized)
    overnight_range_score: float
    or_quality_score: float
    news_risk_penalty: float
    vol_regime_score: float
    expectancy_score: float
    
    # Metadata
    overnight_range_norm: float  # Actual overnight range / ADR
    expected_or_width_norm: float
    recent_win_rate: float
    recent_expectancy: float
    recent_trade_count: int
    
    # Recommendation
    priority: int  # 1 = highest priority
    recommended_watch: bool
    reason: str


class PreSessionRanker:
    """Rank instruments for trading priority before session."""
    
    def __init__(
        self,
        weight_overnight: float = 0.25,
        weight_or_quality: float = 0.20,
        weight_news_risk: float = 0.15,
        weight_vol_regime: float = 0.20,
        weight_expectancy: float = 0.20,
        lookback_trades: int = 50
    ):
        """Initialize ranker.
        
        Args:
            weight_overnight: Weight for overnight range component
            weight_or_quality: Weight for expected OR quality
            weight_news_risk: Weight for news risk penalty
            weight_vol_regime: Weight for volatility regime alignment
            weight_expectancy: Weight for recent expectancy
            lookback_trades: Number of recent trades for expectancy calc
        """
        self.weight_overnight = weight_overnight
        self.weight_or_quality = weight_or_quality
        self.weight_news_risk = weight_news_risk
        self.weight_vol_regime = weight_vol_regime
        self.weight_expectancy = weight_expectancy
        self.lookback_trades = lookback_trades
        
        # Historical data storage
        self.instrument_history: Dict[str, List[dict]] = {}
        self.trade_history: Dict[str, List[dict]] = {}
    
    def update_history(
        self,
        symbol: str,
        trading_date: date,
        overnight_high: float,
        overnight_low: float,
        or_width_norm: float,
        session_adr: float
    ):
        """Update historical data for an instrument.
        
        Args:
            symbol: Instrument symbol
            trading_date: Trading date
            overnight_high: Overnight session high
            overnight_low: Overnight session low
            or_width_norm: Normalized OR width (width / ATR)
            session_adr: Session's actual daily range
        """
        if symbol not in self.instrument_history:
            self.instrument_history[symbol] = []
        
        self.instrument_history[symbol].append({
            'date': trading_date,
            'overnight_high': overnight_high,
            'overnight_low': overnight_low,
            'or_width_norm': or_width_norm,
            'session_adr': session_adr
        })
        
        # Keep last 100 sessions
        if len(self.instrument_history[symbol]) > 100:
            self.instrument_history[symbol].pop(0)
    
    def update_trade_history(
        self,
        symbol: str,
        trade_date: date,
        expectancy_r: float,
        win: bool
    ):
        """Update trade history for an instrument.
        
        Args:
            symbol: Instrument symbol
            trade_date: Trade date
            expectancy_r: Trade R-multiple
            win: Whether trade was a winner
        """
        if symbol not in self.trade_history:
            self.trade_history[symbol] = []
        
        self.trade_history[symbol].append({
            'date': trade_date,
            'expectancy_r': expectancy_r,
            'win': win
        })
        
        # Keep last 200 trades
        if len(self.trade_history[symbol]) > 200:
            self.trade_history[symbol].pop(0)
    
    def rank_instruments(
        self,
        instruments: Dict[str, any],  # symbol -> config
        overnight_data: Dict[str, Tuple[float, float]],  # symbol -> (high, low)
        trading_date: date,
        news_events: Dict[str, float] = None  # symbol -> risk_score (0-1)
    ) -> List[InstrumentScore]:
        """Rank instruments for trading priority.
        
        Args:
            instruments: Dict of symbol -> instrument config
            overnight_data: Dict of symbol -> (overnight_high, overnight_low)
            trading_date: Current trading date
            news_events: Optional dict of symbol -> news risk score
        
        Returns:
            List of InstrumentScore objects, sorted by priority
        """
        scores = []
        
        for symbol, config in instruments.items():
            # Get overnight range
            if symbol in overnight_data:
                overnight_high, overnight_low = overnight_data[symbol]
            else:
                # No overnight data, use neutral values
                overnight_high = config.typical_adr * 0.5
                overnight_low = 0.0
            
            overnight_range = overnight_high - overnight_low
            overnight_range_norm = overnight_range / config.typical_adr if config.typical_adr > 0 else 0.5
            
            # Calculate component scores
            overnight_score = self._score_overnight_range(overnight_range_norm)
            or_quality_score = self._score_or_quality(symbol, config)
            news_risk_penalty = self._score_news_risk(symbol, news_events)
            vol_regime_score = self._score_vol_regime(symbol, overnight_range_norm)
            expectancy_score = self._score_expectancy(symbol)
            
            # Calculate total weighted score
            total_score = (
                self.weight_overnight * overnight_score +
                self.weight_or_quality * or_quality_score +
                self.weight_news_risk * (1.0 - news_risk_penalty) +  # Higher risk = lower score
                self.weight_vol_regime * vol_regime_score +
                self.weight_expectancy * expectancy_score
            )
            
            # Get recent performance stats
            recent_stats = self._get_recent_stats(symbol)
            
            # Determine reason
            reason = self._generate_reason(
                overnight_score, or_quality_score, news_risk_penalty,
                vol_regime_score, expectancy_score
            )
            
            # Create score object
            score_obj = InstrumentScore(
                symbol=symbol,
                total_score=total_score,
                overnight_range_score=overnight_score,
                or_quality_score=or_quality_score,
                news_risk_penalty=news_risk_penalty,
                vol_regime_score=vol_regime_score,
                expectancy_score=expectancy_score,
                overnight_range_norm=overnight_range_norm,
                expected_or_width_norm=recent_stats['avg_or_width_norm'],
                recent_win_rate=recent_stats['win_rate'],
                recent_expectancy=recent_stats['expectancy'],
                recent_trade_count=recent_stats['trade_count'],
                priority=0,  # Will be assigned after sorting
                recommended_watch=total_score >= 0.6,  # Threshold for recommendation
                reason=reason
            )
            
            scores.append(score_obj)
        
        # Sort by total score (descending)
        scores.sort(key=lambda x: x.total_score, reverse=True)
        
        # Assign priorities
        for idx, score in enumerate(scores, 1):
            score.priority = idx
        
        return scores
    
    def _score_overnight_range(self, overnight_range_norm: float) -> float:
        """Score overnight range (higher = more movement, more opportunity).
        
        Optimal range: 0.3 - 0.7 of typical ADR
        
        Args:
            overnight_range_norm: Overnight range / typical ADR
        
        Returns:
            Score 0-1
        """
        if overnight_range_norm < 0.15:
            return 0.3  # Too quiet
        elif overnight_range_norm < 0.30:
            return 0.6  # Moderate
        elif overnight_range_norm <= 0.70:
            return 1.0  # Ideal range
        elif overnight_range_norm <= 1.00:
            return 0.7  # High but manageable
        else:
            return 0.4  # Possibly exhausted
    
    def _score_or_quality(self, symbol: str, config: any) -> float:
        """Score expected OR quality based on history.
        
        Args:
            symbol: Instrument symbol
            config: Instrument config
        
        Returns:
            Score 0-1
        """
        if symbol not in self.instrument_history or len(self.instrument_history[symbol]) < 5:
            return 0.5  # Neutral if no history
        
        history = self.instrument_history[symbol]
        recent_or_widths = [h['or_width_norm'] for h in history[-20:]]
        
        if len(recent_or_widths) == 0:
            return 0.5
        
        # Ideal OR width: within validity bounds
        avg_width = np.mean(recent_or_widths)
        
        # Check if typically within valid bounds
        min_valid = config.validity_min_width_norm
        max_valid = config.validity_max_width_norm
        
        if min_valid <= avg_width <= max_valid:
            return 1.0  # Perfect
        elif avg_width < min_valid:
            # Too narrow on average
            return 0.5 + 0.5 * (avg_width / min_valid)
        else:
            # Too wide on average
            return 0.5 + 0.5 * (max_valid / avg_width)
    
    def _score_news_risk(
        self,
        symbol: str,
        news_events: Dict[str, float] = None
    ) -> float:
        """Score news risk (higher = more risk).
        
        Args:
            symbol: Instrument symbol
            news_events: Dict of symbol -> risk score (0-1)
        
        Returns:
            Risk score 0-1 (0 = no risk, 1 = high risk)
        """
        if news_events and symbol in news_events:
            return news_events[symbol]
        return 0.0  # No news risk by default
    
    def _score_vol_regime(self, symbol: str, overnight_range_norm: float) -> float:
        """Score volatility regime alignment.
        
        Args:
            symbol: Instrument symbol
            overnight_range_norm: Current overnight range / ADR
        
        Returns:
            Score 0-1
        """
        if symbol not in self.instrument_history or len(self.instrument_history[symbol]) < 10:
            return 0.5  # Neutral
        
        history = self.instrument_history[symbol]
        recent_ranges = [
            (h['overnight_high'] - h['overnight_low']) / h['session_adr']
            for h in history[-20:]
            if h['session_adr'] > 0
        ]
        
        if len(recent_ranges) == 0:
            return 0.5
        
        # Check if current range is typical
        avg_range = np.mean(recent_ranges)
        std_range = np.std(recent_ranges)
        
        if std_range == 0:
            return 0.5
        
        # Z-score
        z = abs(overnight_range_norm - avg_range) / std_range
        
        # Prefer consistent regime (low z-score)
        if z < 0.5:
            return 1.0  # Very consistent
        elif z < 1.0:
            return 0.8  # Moderately consistent
        elif z < 1.5:
            return 0.6  # Slightly unusual
        else:
            return 0.4  # Unusual volatility
    
    def _score_expectancy(self, symbol: str) -> float:
        """Score recent expectancy.
        
        Args:
            symbol: Instrument symbol
        
        Returns:
            Score 0-1
        """
        if symbol not in self.trade_history or len(self.trade_history[symbol]) < 3:
            return 0.5  # Neutral if no history
        
        recent_trades = self.trade_history[symbol][-self.lookback_trades:]
        expectancies = [t['expectancy_r'] for t in recent_trades]
        
        if len(expectancies) == 0:
            return 0.5
        
        avg_expectancy = np.mean(expectancies)
        
        # Map expectancy to 0-1 score
        # -1R -> 0.0, 0R -> 0.5, +1R -> 1.0
        score = 0.5 + (avg_expectancy * 0.5)
        return np.clip(score, 0.0, 1.0)
    
    def _get_recent_stats(self, symbol: str) -> dict:
        """Get recent performance statistics.
        
        Args:
            symbol: Instrument symbol
        
        Returns:
            Dict with stats
        """
        # OR quality stats
        avg_or_width = 0.5
        if symbol in self.instrument_history and len(self.instrument_history[symbol]) > 0:
            widths = [h['or_width_norm'] for h in self.instrument_history[symbol][-20:]]
            if len(widths) > 0:
                avg_or_width = np.mean(widths)
        
        # Trade stats
        win_rate = 0.0
        expectancy = 0.0
        trade_count = 0
        
        if symbol in self.trade_history and len(self.trade_history[symbol]) > 0:
            recent = self.trade_history[symbol][-self.lookback_trades:]
            trade_count = len(recent)
            wins = sum(1 for t in recent if t['win'])
            win_rate = wins / trade_count if trade_count > 0 else 0.0
            expectancy = np.mean([t['expectancy_r'] for t in recent])
        
        return {
            'avg_or_width_norm': avg_or_width,
            'win_rate': win_rate,
            'expectancy': expectancy,
            'trade_count': trade_count
        }
    
    def _generate_reason(
        self,
        overnight_score: float,
        or_quality_score: float,
        news_risk_penalty: float,
        vol_regime_score: float,
        expectancy_score: float
    ) -> str:
        """Generate human-readable reason for ranking.
        
        Args:
            Component scores
        
        Returns:
            Reason string
        """
        # Find dominant factors
        factors = []
        
        if overnight_score >= 0.8:
            factors.append("optimal overnight range")
        elif overnight_score <= 0.4:
            factors.append("poor overnight range")
        
        if or_quality_score >= 0.8:
            factors.append("good historical OR quality")
        
        if news_risk_penalty >= 0.5:
            factors.append("high news risk")
        
        if vol_regime_score >= 0.8:
            factors.append("consistent volatility")
        
        if expectancy_score >= 0.7:
            factors.append("strong recent performance")
        elif expectancy_score <= 0.3:
            factors.append("weak recent performance")
        
        if len(factors) == 0:
            return "neutral conditions"
        
        return "; ".join(factors)
    
    def get_watch_list(
        self,
        scores: List[InstrumentScore],
        max_instruments: int = 3
    ) -> List[str]:
        """Get recommended watch list.
        
        Args:
            scores: List of InstrumentScore objects
            max_instruments: Maximum instruments to watch
        
        Returns:
            List of symbols to watch
        """
        # Get top-scored instruments that are recommended
        recommended = [s for s in scores if s.recommended_watch]
        top_instruments = recommended[:max_instruments]
        
        return [s.symbol for s in top_instruments]
    
    def print_rankings(self, scores: List[InstrumentScore]):
        """Print rankings in a formatted table.
        
        Args:
            scores: List of InstrumentScore objects
        """
        logger.info("\n" + "="*100)
        logger.info("PRE-SESSION INSTRUMENT RANKINGS")
        logger.info("="*100)
        
        header = f"{'Rank':<6} {'Symbol':<8} {'Score':<8} {'Watch':<8} {'Reason':<50}"
        logger.info(header)
        logger.info("-"*100)
        
        for score in scores:
            watch_str = "✓ YES" if score.recommended_watch else "  No"
            logger.info(
                f"{score.priority:<6} {score.symbol:<8} {score.total_score:>6.3f}  {watch_str:<8} {score.reason[:48]}"
            )
        
        logger.info("="*100)
        logger.info(f"Recommended Watch List: {', '.join(self.get_watch_list(scores))}")
        logger.info("="*100)
