"""Entry Quality Scoring System

Phase 2 Enhancement #3: Addresses marginal setup quality problem.

Key Findings from Phase 1 Analysis:
- All setups treated equally regardless of quality
- Marginal setups allowed in non-optimal conditions
- No objective quality measurement

Solution:
- 0-100 scoring system based on multiple factors
- Components: Pattern (40) + OFI (30) + Context (20) + Time (10)
- Filter out lowest-quality setups (< 50 = D-grade)

Expected Impact:
- Filter out 30-40% of lowest quality setups
- Improve win rate from 56.9% to 60%+
- Reduce large losses by avoiding marginal entries
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any
import pandas as pd
from loguru import logger


@dataclass
class QualityScore:
    """Entry quality score breakdown.
    
    Attributes:
        total: Total quality score (0-100)
        pattern_score: Pattern quality component (0-40)
        ofi_score: Order flow confirmation component (0-30)
        context_score: Market context component (0-20)
        time_score: Time of day component (0-10)
        grade: Letter grade (A/B/C/D/F)
        components: Detailed breakdown of scoring
    """
    total: int
    pattern_score: int
    ofi_score: int
    context_score: int
    time_score: int
    grade: str
    components: Dict[str, Any]


class EntryQualityScorer:
    """Score trade setup quality on 0-100 scale.
    
    Scoring Components:
    1. Pattern Quality (0-40): Drive range, tape decline, volume
    2. Order Flow (0-30): OFI confirmation, bid/ask imbalance
    3. Market Context (0-20): Trend alignment, volatility regime
    4. Time of Day (0-10): Prime time bonus
    
    Grading Scale:
    - A-grade: 80-100 (excellent setups)
    - B-grade: 65-79 (good setups)
    - C-grade: 50-64 (acceptable setups)
    - D-grade: 35-49 (marginal setups - caution)
    - F-grade: 0-34 (poor setups - skip)
    
    Example:
        >>> scorer = EntryQualityScorer()
        >>> setup = {...}  # Setup parameters
        >>> score = scorer.calculate_quality(setup, market_state, mbp_data)
        >>> print(f"Quality: {score.total} ({score.grade})")
        >>> if score.total >= 65:
        ...     # Take the trade
    """
    
    def __init__(
        self,
        min_trade_quality: int = 50,  # C-grade minimum
        enable_ofi_scoring: bool = True,
        enable_context_scoring: bool = True,
        enable_time_scoring: bool = True,
    ):
        """Initialize entry quality scorer.
        
        Args:
            min_trade_quality: Minimum quality score to take trade
            enable_ofi_scoring: Enable order flow scoring component
            enable_context_scoring: Enable market context scoring
            enable_time_scoring: Enable time of day scoring
        """
        self.min_trade_quality = min_trade_quality
        self.enable_ofi_scoring = enable_ofi_scoring
        self.enable_context_scoring = enable_context_scoring
        self.enable_time_scoring = enable_time_scoring
        
        logger.info(
            f"EntryQualityScorer initialized: min_quality={min_trade_quality}, "
            f"ofi={enable_ofi_scoring}, context={enable_context_scoring}, "
            f"time={enable_time_scoring}"
        )
    
    def calculate_quality(
        self,
        setup: Dict[str, Any],
        market_state: Optional[Dict[str, Any]] = None,
        mbp_data: Optional[pd.DataFrame] = None,
        timestamp: Optional[datetime] = None,
    ) -> QualityScore:
        """Calculate comprehensive entry quality score.
        
        Args:
            setup: Setup parameters (drive_range, tape_decline, volume_ratio, etc)
            market_state: Market state (trend, volatility_regime, regime_confidence)
            mbp_data: MBP-10 order book data for OFI calculation
            timestamp: Entry timestamp for time-of-day scoring
            
        Returns:
            QualityScore with total score and breakdown
        """
        # Component 1: Pattern Quality (0-40 points)
        pattern_score, pattern_details = self._score_pattern_quality(setup)
        
        # Component 2: Order Flow Confirmation (0-30 points)
        if self.enable_ofi_scoring:
            # OFI can come from setup dict or be calculated from mbp_data
            ofi_score, ofi_details = self._score_order_flow(setup, mbp_data)
        else:
            ofi_score, ofi_details = 0, {'reason': 'OFI scoring disabled'}
        
        # Component 3: Market Context (0-20 points)
        if self.enable_context_scoring and market_state is not None:
            context_score, context_details = self._score_market_context(setup, market_state)
        else:
            context_score, context_details = 0, {'reason': 'Context scoring disabled or no data'}
        
        # Component 4: Time of Day (0-10 points)
        if self.enable_time_scoring and timestamp is not None:
            time_score, time_details = self._score_time_of_day(timestamp)
        else:
            time_score, time_details = 0, {'reason': 'Time scoring disabled or no timestamp'}
        
        # Calculate total
        total = pattern_score + ofi_score + context_score + time_score
        total = min(100, max(0, total))  # Clamp to 0-100
        
        # Determine grade
        grade = self._calculate_grade(total)
        
        # Compile components
        components = {
            'pattern': pattern_details,
            'ofi': ofi_details,
            'context': context_details,
            'time': time_details,
        }
        
        return QualityScore(
            total=total,
            pattern_score=pattern_score,
            ofi_score=ofi_score,
            context_score=context_score,
            time_score=time_score,
            grade=grade,
            components=components,
        )
    
    def _score_pattern_quality(self, setup: Dict[str, Any]) -> tuple[int, Dict[str, Any]]:
        """Score the setup pattern quality (0-40 points).
        
        Factors:
        - Drive range (0-15 points)
        - Tape decline (0-15 points)
        - Volume ratio (0-10 points)
        
        Args:
            setup: Setup parameters
            
        Returns:
            Tuple of (score, details)
        """
        score = 0
        details = {}
        
        # Drive range quality (0-15 points)
        drive_range = setup.get('drive_range', 0)
        if drive_range >= 5.0:
            drive_score = 15
        elif drive_range >= 4.0:
            drive_score = 12
        elif drive_range >= 3.5:
            drive_score = 10
        elif drive_range >= 3.0:
            drive_score = 7
        elif drive_range >= 2.5:
            drive_score = 5
        else:
            drive_score = 0
        
        score += drive_score
        details['drive_range'] = {
            'value': drive_range,
            'score': drive_score,
            'max': 15
        }
        
        # Tape decline quality (0-15 points)
        tape_decline = setup.get('tape_decline', 0)
        if tape_decline >= 0.5:
            tape_score = 15
        elif tape_decline >= 0.4:
            tape_score = 12
        elif tape_decline >= 0.3:
            tape_score = 10
        elif tape_decline >= 0.25:
            tape_score = 7
        elif tape_decline >= 0.2:
            tape_score = 5
        else:
            tape_score = 0
        
        score += tape_score
        details['tape_decline'] = {
            'value': tape_decline,
            'score': tape_score,
            'max': 15
        }
        
        # Volume ratio quality (0-10 points)
        volume_ratio = setup.get('volume_ratio', 1.0)
        if volume_ratio >= 2.0:
            volume_score = 10
        elif volume_ratio >= 1.5:
            volume_score = 7
        elif volume_ratio >= 1.2:
            volume_score = 5
        else:
            volume_score = 0
        
        score += volume_score
        details['volume_ratio'] = {
            'value': volume_ratio,
            'score': volume_score,
            'max': 10
        }
        
        details['total'] = score
        return score, details
    
    def _score_order_flow(
        self,
        setup: Dict[str, Any],
        mbp_data: pd.DataFrame,
    ) -> tuple[int, Dict[str, Any]]:
        """Score order flow confirmation (0-30 points).
        
        Uses OFI (Order Flow Imbalance) to confirm trade direction.
        For longs, want positive OFI (buying pressure).
        For shorts, want negative OFI (selling pressure).
        
        Args:
            setup: Setup parameters (must include 'direction')
            mbp_data: MBP-10 order book data
            
        Returns:
            Tuple of (score, details)
        """
        score = 0
        details = {}
        
        direction = setup.get('direction', 'long')
        
        # Calculate OFI (simplified - in production, use full MBP-10 calculation)
        # For now, assume OFI is provided in setup or calculate simple version
        ofi = setup.get('ofi', 0.0)
        
        # If OFI not in setup, try to calculate from mbp_data
        if ofi == 0.0 and mbp_data is not None and len(mbp_data) > 0:
            # Simple OFI approximation: recent bid/ask imbalance
            # In production, this would use full MBP-10 depth and updates
            if 'bid_size' in mbp_data.columns and 'ask_size' in mbp_data.columns:
                recent = mbp_data.tail(10)
                total_bid = recent['bid_size'].sum()
                total_ask = recent['ask_size'].sum()
                if total_bid + total_ask > 0:
                    ofi = (total_bid - total_ask) / (total_bid + total_ask)
        
        # Score based on direction and OFI alignment
        if direction.lower() == 'long':
            # For longs, want positive OFI (buying pressure)
            if ofi > 0.6:
                score = 30  # Strong buying
            elif ofi > 0.4:
                score = 20  # Moderate buying
            elif ofi > 0.2:
                score = 10  # Weak buying
            elif ofi > 0:
                score = 5   # Slight buying
            else:
                score = 0   # No confirmation or negative
        else:
            # For shorts, want negative OFI (selling pressure)
            if ofi < -0.6:
                score = 30  # Strong selling
            elif ofi < -0.4:
                score = 20  # Moderate selling
            elif ofi < -0.2:
                score = 10  # Weak selling
            elif ofi < 0:
                score = 5   # Slight selling
            else:
                score = 0   # No confirmation or positive
        
        details['ofi'] = ofi
        details['direction'] = direction
        details['score'] = score
        details['alignment'] = 'good' if score >= 20 else ('fair' if score >= 10 else 'poor')
        
        return score, details
    
    def _score_market_context(
        self,
        setup: Dict[str, Any],
        market_state: Dict[str, Any],
    ) -> tuple[int, Dict[str, Any]]:
        """Score market context alignment (0-20 points).
        
        Factors:
        - Trend alignment (0-10 points)
        - Volatility regime match (0-5 points)
        - Regime confidence (0-5 points)
        
        Args:
            setup: Setup parameters (must include 'direction')
            market_state: Market state information
            
        Returns:
            Tuple of (score, details)
        """
        score = 0
        details = {}
        
        direction = setup.get('direction', 'long')
        
        # Trend alignment (0-10 points)
        trend = market_state.get('trend', 0)
        if (direction.lower() == 'long' and trend > 0) or \
           (direction.lower() == 'short' and trend < 0):
            # Aligned with trend
            if abs(trend) > 0.7:
                trend_score = 10  # Strong trend alignment
            elif abs(trend) > 0.4:
                trend_score = 7   # Moderate trend alignment
            else:
                trend_score = 5   # Weak trend alignment
        else:
            # Counter-trend
            trend_score = 0
        
        score += trend_score
        details['trend'] = {
            'value': trend,
            'direction': direction,
            'score': trend_score,
            'aligned': trend_score > 0
        }
        
        # Volatility regime match (0-5 points)
        # Opening Drive Reversal performs best in medium volatility
        volatility_regime = market_state.get('volatility_regime', 'MEDIUM')
        if volatility_regime == 'MEDIUM':
            vol_score = 5
        elif volatility_regime in ['LOW', 'HIGH']:
            vol_score = 3
        else:
            vol_score = 0
        
        score += vol_score
        details['volatility_regime'] = {
            'value': volatility_regime,
            'score': vol_score,
            'optimal': volatility_regime == 'MEDIUM'
        }
        
        # Regime confidence (0-5 points)
        regime_confidence = market_state.get('regime_confidence', 0.5)
        if regime_confidence > 0.8:
            confidence_score = 5
        elif regime_confidence > 0.6:
            confidence_score = 3
        else:
            confidence_score = 0
        
        score += confidence_score
        details['regime_confidence'] = {
            'value': regime_confidence,
            'score': confidence_score
        }
        
        details['total'] = score
        return score, details
    
    def _score_time_of_day(self, timestamp: datetime) -> tuple[int, Dict[str, Any]]:
        """Score time of day (0-10 points).
        
        Based on Phase 1 findings:
        - Morning (9-11 ET): Best performance (0.145R avg) → 10 points
        - Afternoon (14-16 ET): Decent performance (0.021R avg) → 5 points
        - Other times: Poor performance (-0.067R avg) → 0 points
        
        Args:
            timestamp: Entry timestamp
            
        Returns:
            Tuple of (score, details)
        """
        hour = timestamp.hour
        
        # Morning prime time (9-11 ET)
        if 9 <= hour < 11:
            score = 10
            window = 'PRIME'
        # Afternoon good time (14-16 ET)
        elif 14 <= hour < 16:
            score = 5
            window = 'GOOD'
        # Other market hours
        elif 9 <= hour < 16:
            score = 0
            window = 'AVOID'
        # Outside market hours
        else:
            score = 0
            window = 'OFF_HOURS'
        
        details = {
            'hour': hour,
            'window': window,
            'score': score
        }
        
        return score, details
    
    def _calculate_grade(self, total_score: int) -> str:
        """Calculate letter grade from total score.
        
        Args:
            total_score: Total quality score (0-100)
            
        Returns:
            Letter grade (A/B/C/D/F)
        """
        if total_score >= 80:
            return 'A'
        elif total_score >= 65:
            return 'B'
        elif total_score >= 50:
            return 'C'
        elif total_score >= 35:
            return 'D'
        else:
            return 'F'
    
    def should_trade(self, quality_score: QualityScore) -> tuple[bool, str]:
        """Determine if setup meets minimum quality threshold.
        
        Args:
            quality_score: Calculated quality score
            
        Returns:
            Tuple of (should_trade, reason)
        """
        if quality_score.total >= self.min_trade_quality:
            return True, f"Quality {quality_score.total} ({quality_score.grade}) meets threshold"
        else:
            return False, f"Quality {quality_score.total} ({quality_score.grade}) below threshold {self.min_trade_quality}"
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get scorer statistics.
        
        Returns:
            Dictionary with configuration
        """
        return {
            'min_trade_quality': self.min_trade_quality,
            'enable_ofi_scoring': self.enable_ofi_scoring,
            'enable_context_scoring': self.enable_context_scoring,
            'enable_time_scoring': self.enable_time_scoring,
            'grading_scale': {
                'A': '80-100',
                'B': '65-79',
                'C': '50-64',
                'D': '35-49',
                'F': '0-34',
            }
        }


class ConservativeQualityScorer(EntryQualityScorer):
    """Conservative quality scorer (B-grade minimum).
    
    Use this for:
    - Initial deployment
    - After losing streaks
    - Low confidence market conditions
    """
    
    def __init__(self):
        """Initialize conservative scorer."""
        super().__init__(
            min_trade_quality=65,  # B-grade minimum
            enable_ofi_scoring=True,
            enable_context_scoring=True,
            enable_time_scoring=True,
        )
        logger.info("ConservativeQualityScorer initialized: B-grade minimum (65+)")


class AggressiveQualityScorer(EntryQualityScorer):
    """Aggressive quality scorer (C-grade minimum).
    
    Use this for:
    - After validation shows good results
    - Winning streaks
    - High confidence market conditions
    """
    
    def __init__(self):
        """Initialize aggressive scorer."""
        super().__init__(
            min_trade_quality=50,  # C-grade minimum
            enable_ofi_scoring=True,
            enable_context_scoring=True,
            enable_time_scoring=True,
        )
        logger.info("AggressiveQualityScorer initialized: C-grade minimum (50+)")

