"""Enhanced trade models for multi-instrument ORB strategy with comprehensive logging."""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
import json


class Direction(str, Enum):
    """Trade direction."""
    LONG = "LONG"
    SHORT = "SHORT"


class ExitReason(str, Enum):
    """Trade exit reason."""
    STOP = "STOP"
    TARGET1 = "TARGET1"
    TARGET2 = "TARGET2"
    RUNNER = "RUNNER"
    EOD = "EOD"
    TIME_STOP = "TIME_STOP"
    BREAKEVEN = "BREAKEVEN"
    GOVERNANCE_HALT = "GOVERNANCE_HALT"


@dataclass
class InstrumentParams:
    """Instrument-specific parameters."""
    symbol: str
    display_name: str
    tick_size: float
    tick_value: float  # Full contract
    tick_value_micro: float  # Micro contract
    session_start: str  # "HH:MM" CT
    session_end: str  # "HH:MM" CT
    base_or_minutes: int
    min_or_minutes: int
    max_or_minutes: int
    base_buffer_points: float
    min_stop_points: float
    typical_adr: float  # For normalization
    

@dataclass
class ORMetrics:
    """Opening range metrics and validation."""
    start_ts: datetime
    end_ts: datetime
    high: float
    low: float
    width: float
    width_norm: float  # width / ATR
    width_percentile: float  # Rolling 30-day percentile
    center: float  # (high + low) / 2
    center_vs_prior_mid: float  # Bias context
    overlap_ratio: float  # Overlap with prior day value area
    overnight_range_util: float  # overnight_range / ADR
    is_valid: bool
    invalid_reason: Optional[str] = None
    adaptive_length_used: int = 15


@dataclass
class VolumeMetrics:
    """Goldilocks volume metrics."""
    cum_volume_or: float
    expected_volume_or: float
    cum_vol_ratio: float  # cum_volume / expected_volume
    vol_z_score: float  # Z-score deviation
    spike_detected: bool
    max_spike_ratio: float  # Max single bar spike ratio
    opening_drive_energy: float  # Directional energy
    volume_quality_score: float  # Composite 0-1 score
    passes_goldilocks: bool


@dataclass
class BreakoutContext:
    """Breakout timing and context."""
    breakout_ts: datetime
    breakout_delay_minutes: float  # Minutes from OR end
    direction: Direction
    trigger_price: float
    buffer_used: float
    is_retest: bool  # Was this a retest breakout?
    had_wick_first: bool  # Did it wick first before body close?
    

@dataclass
class Target:
    """Individual profit target."""
    price: float
    r_multiple: float
    size_fraction: float  # e.g., 0.4 for 40%
    hit: bool = False
    hit_ts: Optional[datetime] = None


@dataclass
class RiskMetrics:
    """Risk and position sizing metrics."""
    entry_price: float
    initial_stop_price: float
    stop_distance_points: float
    stop_distance_dollars: float
    position_size: int  # Number of contracts
    dollar_risk: float  # Total $ at risk
    account_risk_pct: float  # % of account
    targets: List[Target] = field(default_factory=list)


@dataclass
class TradeOutcome:
    """Trade outcome and performance metrics."""
    exit_ts: datetime
    exit_price: float
    exit_reason: ExitReason
    realized_r: float
    realized_dollars: float
    mfe_r: float  # Max favorable excursion
    mae_r: float  # Max adverse excursion
    mfe_ts: Optional[datetime] = None
    mae_ts: Optional[datetime] = None
    bars_held: int = 0
    minutes_held: float = 0.0
    reached_1r: bool = False
    time_to_1r_minutes: Optional[float] = None


@dataclass
class FactorSnapshot:
    """Snapshot of all factor states at signal time."""
    # Volume factors
    volume_quality_score: float
    volume_passes: bool
    
    # Structure factors
    or_valid: bool
    or_width_norm: float
    or_percentile: float
    
    # Bias factors
    center_vs_prior_mid: float
    overnight_bias: float
    
    # Cross-instrument (if applicable)
    es_nq_corr: Optional[float] = None
    
    # Volatility regime
    norm_vol: float = 0.0
    adx: Optional[float] = None
    
    # Directional alignment
    bias_score: float = 0.0
    

@dataclass
class ComprehensiveTrade:
    """Complete trade record with all metadata for analysis and journaling."""
    
    # Identification
    trade_id: str  # configHash_date_instrumentSeq
    instrument: str
    date: str  # Session date
    config_hash: str
    
    # Opening Range
    or_metrics: ORMetrics
    
    # Volume Analysis
    volume_metrics: VolumeMetrics
    
    # Breakout
    breakout_context: BreakoutContext
    
    # Risk Management
    risk_metrics: RiskMetrics
    
    # Factors at Signal
    factors: FactorSnapshot
    
    # Outcome (filled after exit)
    outcome: Optional[TradeOutcome] = None
    
    # Equity tracking
    equity_r_before: float = 0.0
    equity_r_after: float = 0.0
    
    # Governance context
    daily_trade_number: int = 1
    cumulative_daily_r: float = 0.0
    
    # Regime labels
    regime_labels: Dict[str, Any] = field(default_factory=dict)
    
    # Baseline comparisons (optional)
    baseline_outcomes: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with proper serialization."""
        data = asdict(self)
        
        # Convert enums to strings
        if 'breakout_context' in data and 'direction' in data['breakout_context']:
            data['breakout_context']['direction'] = data['breakout_context']['direction']
        
        if 'outcome' in data and data['outcome'] and 'exit_reason' in data['outcome']:
            data['outcome']['exit_reason'] = data['outcome']['exit_reason']
        
        # Convert datetimes to ISO strings
        for key in ['or_metrics', 'breakout_context', 'outcome']:
            if key in data and data[key]:
                for subkey, value in data[key].items():
                    if isinstance(value, datetime):
                        data[key][subkey] = value.isoformat()
        
        return data
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ComprehensiveTrade':
        """Create from dictionary."""
        # This would need proper deserialization logic
        # Placeholder for now
        raise NotImplementedError("Deserialization not yet implemented")


@dataclass
class SessionSummary:
    """Summary of a trading session across all instruments."""
    date: str
    instruments_traded: List[str]
    total_trades: int
    winning_trades: int
    losing_trades: int
    total_r: float
    total_dollars: float
    largest_win_r: float
    largest_loss_r: float
    daily_drawdown_pct: float
    daily_limit_used_pct: float
    trades_detail: List[ComprehensiveTrade] = field(default_factory=list)


@dataclass
class InstrumentRanking:
    """Pre-session instrument ranking."""
    instrument: str
    rank_score: float
    overnight_range_norm: float
    expected_or_quality: float
    news_risk_penalty: float
    vol_regime_alignment: float
    recent_expectancy: float
    recommended_priority: int  # 1 = highest


@dataclass
class BaselineComparison:
    """Baseline strategy comparison."""
    strategy_name: str
    total_trades: int
    expectancy: float
    win_rate: float
    edge_delta_vs_actual: float  # Difference in expectancy
