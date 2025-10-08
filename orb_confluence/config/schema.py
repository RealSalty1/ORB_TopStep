"""Pydantic configuration schemas with comprehensive validation.

All strategy parameters are defined here with cross-field validation rules.
"""

from datetime import time
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class SessionMode(str, Enum):
    """Trading session mode."""

    RTH = "rth"  # Regular trading hours
    ETH = "eth"  # Extended trading hours
    FULL = "full"  # 24-hour


class StopMode(str, Enum):
    """Stop placement mode."""

    OR_OPPOSITE = "or_opposite"
    SWING = "swing"
    ATR_CAPPED = "atr_capped"


class InstrumentConfig(BaseModel):
    """Instrument configuration."""

    symbol: str = Field(..., description="Target futures symbol (e.g., ES)")
    proxy_symbol: str = Field(..., description="Proxy symbol for free data (e.g., SPY)")
    data_source: str = Field(..., description="Data source: yahoo, binance, synthetic")
    session_mode: SessionMode = Field(SessionMode.RTH, description="Trading session type")
    session_start: time = Field(..., description="Session start time (exchange local)")
    session_end: time = Field(..., description="Session end time (exchange local)")
    timezone: str = Field("America/Chicago", description="Exchange timezone")
    tick_size: float = Field(..., gt=0, description="Minimum price increment")
    point_value: float = Field(..., gt=0, description="Dollar value per full point")
    enabled: bool = Field(True, description="Enable trading this instrument")

    @field_validator("symbol", "proxy_symbol")
    @classmethod
    def validate_symbol_format(cls, v: str) -> str:
        """Ensure symbols are uppercase and non-empty."""
        if not v or not v.strip():
            raise ValueError("Symbol cannot be empty")
        return v.upper().strip()

    @field_validator("data_source")
    @classmethod
    def validate_data_source(cls, v: str) -> str:
        """Validate data source."""
        valid_sources = ["yahoo", "binance", "alphavantage", "synthetic"]
        if v.lower() not in valid_sources:
            raise ValueError(f"Data source must be one of {valid_sources}")
        return v.lower()

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        """Validate timezone string."""
        try:
            import pytz
            pytz.timezone(v)
        except Exception:
            raise ValueError(f"Invalid timezone: {v}")
        return v


class ORBConfig(BaseModel):
    """Opening Range configuration with adaptive duration."""

    base_minutes: int = Field(15, ge=5, le=60, description="Base OR duration (minutes)")
    adaptive: bool = Field(True, description="Use adaptive OR duration based on volatility")

    # Adaptive thresholds
    low_norm_vol: float = Field(
        0.35, ge=0.0, le=2.0, description="Normalized vol threshold for short OR"
    )
    high_norm_vol: float = Field(
        0.85, ge=0.0, le=2.0, description="Normalized vol threshold for long OR"
    )
    short_or_minutes: int = Field(10, ge=5, le=30, description="Short OR duration (minutes)")
    long_or_minutes: int = Field(30, ge=15, le=60, description="Long OR duration (minutes)")

    # Volatility calculation
    atr_period: int = Field(14, ge=5, le=50, description="ATR lookback period")
    intraday_atr_timeframe: str = Field("5min", description="Intraday ATR timeframe")
    daily_atr_timeframe: str = Field("1day", description="Daily ATR timeframe")

    # OR validity filters
    enable_validity_filter: bool = Field(True, description="Require valid OR width")
    min_atr_mult: float = Field(0.25, ge=0.0, description="Minimum OR width as ATR multiple")
    max_atr_mult: float = Field(1.75, ge=0.0, description="Maximum OR width as ATR multiple")

    @model_validator(mode="after")
    def validate_or_params(self) -> "ORBConfig":
        """Validate OR parameter relationships."""
        # ATR multipliers
        if self.min_atr_mult >= self.max_atr_mult:
            raise ValueError(
                f"min_atr_mult ({self.min_atr_mult}) must be < max_atr_mult ({self.max_atr_mult})"
            )

        # Adaptive thresholds
        if self.adaptive:
            if self.low_norm_vol >= self.high_norm_vol:
                raise ValueError(
                    f"low_norm_vol ({self.low_norm_vol}) must be < high_norm_vol ({self.high_norm_vol})"
                )
            if self.short_or_minutes >= self.long_or_minutes:
                raise ValueError(
                    f"short_or_minutes ({self.short_or_minutes}) must be < long_or_minutes ({self.long_or_minutes})"
                )

        return self


class BuffersConfig(BaseModel):
    """Breakout buffer configuration."""

    fixed: float = Field(0.0, ge=0.0, description="Fixed buffer (instrument-specific units)")
    use_atr: bool = Field(False, description="Add ATR-based dynamic buffer")
    atr_mult: float = Field(0.05, ge=0.0, le=0.5, description="ATR buffer multiplier")

    @model_validator(mode="after")
    def validate_buffer(self) -> "BuffersConfig":
        """Ensure at least one buffer type is non-zero."""
        if self.fixed == 0.0 and not self.use_atr:
            raise ValueError("Must have either fixed buffer > 0 or use_atr = True")
        return self


class RelativeVolumeConfig(BaseModel):
    """Relative volume factor configuration."""

    enabled: bool = Field(True, description="Enable relative volume factor")
    lookback: int = Field(20, ge=5, le=100, description="Volume SMA lookback periods")
    spike_mult: float = Field(1.25, ge=1.0, le=5.0, description="Spike threshold multiplier")


class PriceActionConfig(BaseModel):
    """Price action pattern factor configuration."""

    enabled: bool = Field(True, description="Enable price action factor")
    pivot_len: int = Field(3, ge=2, le=10, description="Pivot lookback length")
    enable_engulfing: bool = Field(True, description="Check for engulfing patterns")
    enable_structure: bool = Field(True, description="Check for HH/HL or LL/LH structure")

    @model_validator(mode="after")
    def validate_price_action(self) -> "PriceActionConfig":
        """Ensure at least one pattern type is enabled."""
        if self.enabled and not (self.enable_engulfing or self.enable_structure):
            raise ValueError("At least one pattern type (engulfing or structure) must be enabled")
        return self


class ProfileProxyConfig(BaseModel):
    """Profile proxy factor configuration."""

    enabled: bool = Field(True, description="Enable profile proxy factor")
    val_pct: float = Field(0.25, ge=0.0, le=1.0, description="Value Area Low percentile")
    vah_pct: float = Field(0.75, ge=0.0, le=1.0, description="Value Area High percentile")

    @model_validator(mode="after")
    def validate_profile(self) -> "ProfileProxyConfig":
        """Ensure VAL < VAH."""
        if self.val_pct >= self.vah_pct:
            raise ValueError(f"val_pct ({self.val_pct}) must be < vah_pct ({self.vah_pct})")
        return self


class VWAPConfig(BaseModel):
    """VWAP factor configuration."""

    enabled: bool = Field(False, description="Enable VWAP factor")
    reset_mode: str = Field("session", description="VWAP reset point: session or or_end")

    @field_validator("reset_mode")
    @classmethod
    def validate_reset_mode(cls, v: str) -> str:
        """Validate reset mode."""
        valid_modes = ["session", "or_end"]
        if v not in valid_modes:
            raise ValueError(f"reset_mode must be one of {valid_modes}")
        return v


class ADXConfig(BaseModel):
    """ADX trend regime factor configuration."""

    enabled: bool = Field(False, description="Enable ADX factor")
    period: int = Field(14, ge=5, le=50, description="ADX calculation period")
    threshold: float = Field(18.0, ge=0.0, le=50.0, description="Minimum ADX for trend")


class FactorsConfig(BaseModel):
    """All factor configurations."""

    rel_volume: RelativeVolumeConfig = Field(default_factory=RelativeVolumeConfig)
    price_action: PriceActionConfig = Field(default_factory=PriceActionConfig)
    profile_proxy: ProfileProxyConfig = Field(default_factory=ProfileProxyConfig)
    vwap: VWAPConfig = Field(default_factory=VWAPConfig)
    adx: ADXConfig = Field(default_factory=ADXConfig)

    def count_enabled(self) -> int:
        """Count number of enabled factors."""
        return sum(
            [
                self.rel_volume.enabled,
                self.price_action.enabled,
                self.profile_proxy.enabled,
                self.vwap.enabled,
                self.adx.enabled,
            ]
        )


class ScoringConfig(BaseModel):
    """Confluence scoring configuration."""

    enabled: bool = Field(True, description="Enable confluence scoring gate")
    base_required: int = Field(2, ge=0, le=10, description="Base score required for entry")
    weak_trend_required: int = Field(
        3, ge=0, le=10, description="Score required in weak trend (ADX < threshold)"
    )

    # Factor weights
    weights: Dict[str, float] = Field(
        default_factory=lambda: {
            "price_action": 1.0,
            "rel_vol": 1.0,
            "profile": 1.0,
            "vwap": 1.0,
            "adx": 1.0,
        },
        description="Factor weights for scoring",
    )

    @field_validator("weights")
    @classmethod
    def validate_weights(cls, v: Dict[str, float]) -> Dict[str, float]:
        """Ensure all weights are non-negative."""
        for key, val in v.items():
            if val < 0:
                raise ValueError(f"Weight for {key} must be non-negative, got {val}")
        return v

    @model_validator(mode="after")
    def validate_scoring(self) -> "ScoringConfig":
        """Validate scoring thresholds."""
        if self.base_required > self.weak_trend_required:
            raise ValueError(
                f"base_required ({self.base_required}) should not exceed weak_trend_required ({self.weak_trend_required})"
            )
        return self


class TradeConfig(BaseModel):
    """Trade execution and management configuration."""

    # Stop placement
    stop_mode: StopMode = Field(StopMode.OR_OPPOSITE, description="Stop placement mode")
    extra_stop_buffer: float = Field(
        0.0, ge=0.0, description="Extra buffer beyond structural stop"
    )
    atr_stop_cap_mult: float = Field(
        0.80, ge=0.0, le=3.0, description="ATR cap multiplier for stop distance"
    )

    # Targets and partials
    partials: bool = Field(True, description="Use partial profit targets")
    t1_r: float = Field(1.0, gt=0.0, description="First target R multiple")
    t1_pct: float = Field(0.5, gt=0.0, le=1.0, description="First target position %")
    t2_r: float = Field(1.5, gt=0.0, description="Second target R multiple")
    t2_pct: float = Field(0.25, gt=0.0, le=1.0, description="Second target position %")
    runner_r: float = Field(2.0, gt=0.0, description="Runner target R multiple")

    # Single target mode (when partials=False)
    primary_r: float = Field(1.5, gt=0.0, description="Primary target R when no partials")

    # Breakeven logic
    move_be_at_r: float = Field(
        1.0, gt=0.0, description="Move stop to breakeven after this R achieved"
    )
    be_buffer: float = Field(0.0, ge=0.0, description="Buffer when moving to breakeven (ticks)")

    @model_validator(mode="after")
    def validate_trade_params(self) -> "TradeConfig":
        """Validate trade parameter relationships."""
        if self.partials:
            # Check target percentages sum to <= 1.0
            total_pct = self.t1_pct + self.t2_pct
            if total_pct > 1.0:
                raise ValueError(f"t1_pct + t2_pct ({total_pct}) must be <= 1.0")

            # Check target R progression
            if self.t1_r >= self.t2_r:
                raise ValueError(f"t1_r ({self.t1_r}) must be < t2_r ({self.t2_r})")
            if self.t2_r >= self.runner_r:
                raise ValueError(f"t2_r ({self.t2_r}) must be < runner_r ({self.runner_r})")

            # Validate runner_r > 1.5 when partials enabled
            if self.runner_r <= 1.5:
                raise ValueError(f"runner_r ({self.runner_r}) must be > 1.5 when partials=True")

        return self


class GovernanceConfig(BaseModel):
    """Risk governance and discipline configuration."""

    max_signals_per_day: int = Field(
        3, ge=1, le=10, description="Maximum signals per instrument per day"
    )
    lockout_after_losses: int = Field(
        2, ge=1, le=10, description="Consecutive full-stop losses before lockout"
    )
    max_daily_loss_r: Optional[float] = Field(
        None, ge=0.0, description="Maximum daily loss in R (halts new entries if reached)"
    )
    time_cutoff: Optional[time] = Field(
        None, description="No new entries after this time (exchange local)"
    )
    second_chance_minutes: int = Field(
        30, ge=0, le=120, description="Allow re-break within N minutes after OR"
    )
    flatten_at_session_end: bool = Field(
        True, description="Flatten all positions before session close"
    )


class BacktestConfig(BaseModel):
    """Backtest execution configuration."""

    start_date: str = Field(..., description="Backtest start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="Backtest end date (YYYY-MM-DD)")
    initial_capital: float = Field(100000.0, gt=0.0, description="Initial capital")
    contracts_per_trade: int = Field(1, ge=1, description="Contracts per trade (fixed)")
    conservative_fills: bool = Field(
        True, description="If stop & target both hit in bar, assume stop first"
    )
    random_seed: int = Field(42, description="Random seed for reproducibility")

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        """Validate date format."""
        from datetime import datetime

        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Date must be in YYYY-MM-DD format, got: {v}")
        return v

    @model_validator(mode="after")
    def validate_date_range(self) -> "BacktestConfig":
        """Ensure start_date < end_date."""
        from datetime import datetime

        start = datetime.strptime(self.start_date, "%Y-%m-%d")
        end = datetime.strptime(self.end_date, "%Y-%m-%d")

        if start >= end:
            raise ValueError(f"start_date ({self.start_date}) must be before end_date ({self.end_date})")

        return self


class OptimizationConfig(BaseModel):
    """Optimization configuration (optional)."""

    enabled: bool = Field(False, description="Enable parameter optimization")
    method: str = Field("optuna", description="Optimization method: optuna, grid, random")
    n_trials: int = Field(100, ge=1, description="Number of optimization trials")
    objective: str = Field("expectancy", description="Optimization objective: expectancy, sharpe, profit_factor")
    
    # Parameter ranges to optimize (example structure)
    optimize_params: List[str] = Field(
        default_factory=list,
        description="List of parameter paths to optimize (e.g., 'orb.base_minutes')"
    )

    @field_validator("method")
    @classmethod
    def validate_method(cls, v: str) -> str:
        """Validate optimization method."""
        valid_methods = ["optuna", "grid", "random"]
        if v not in valid_methods:
            raise ValueError(f"method must be one of {valid_methods}")
        return v

    @field_validator("objective")
    @classmethod
    def validate_objective(cls, v: str) -> str:
        """Validate optimization objective."""
        valid_objectives = ["expectancy", "sharpe", "profit_factor", "win_rate", "total_r"]
        if v not in valid_objectives:
            raise ValueError(f"objective must be one of {valid_objectives}")
        return v


class StrategyConfig(BaseModel):
    """Root strategy configuration with full validation."""

    name: str = Field("ORB_Confluence", description="Strategy name")
    version: str = Field("1.0", description="Configuration version")

    instruments: Dict[str, InstrumentConfig] = Field(..., description="Instrument configurations")
    orb: ORBConfig = Field(default_factory=ORBConfig)
    buffers: BuffersConfig = Field(default_factory=BuffersConfig)
    factors: FactorsConfig = Field(default_factory=FactorsConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    trade: TradeConfig = Field(default_factory=TradeConfig)
    governance: GovernanceConfig = Field(default_factory=GovernanceConfig)
    backtest: BacktestConfig = Field(..., description="Backtest parameters")
    optimization: OptimizationConfig = Field(default_factory=OptimizationConfig)

    # Logging
    log_level: str = Field("INFO", description="Logging level")
    log_to_file: bool = Field(True, description="Write logs to file")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return v_upper

    @model_validator(mode="after")
    def validate_strategy(self) -> "StrategyConfig":
        """Cross-field validation."""
        # Ensure at least one instrument is enabled
        if not any(inst.enabled for inst in self.instruments.values()):
            raise ValueError("At least one instrument must be enabled")

        # Check scoring requirements vs available factors
        enabled_factors = self.factors.count_enabled()
        if self.scoring.enabled:
            if self.scoring.base_required > enabled_factors:
                raise ValueError(
                    f"scoring.base_required ({self.scoring.base_required}) exceeds "
                    f"number of enabled factors ({enabled_factors})"
                )
            if self.scoring.weak_trend_required > enabled_factors:
                raise ValueError(
                    f"scoring.weak_trend_required ({self.scoring.weak_trend_required}) exceeds "
                    f"number of enabled factors ({enabled_factors})"
                )

        return self