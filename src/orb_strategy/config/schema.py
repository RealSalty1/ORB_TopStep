"""Pydantic configuration schemas for strategy parameters.

All strategy configuration is defined here and validated on load.
YAML configs are deserialized into these models.
"""

from datetime import time
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator
from ruamel.yaml import YAML


class SessionMode(str, Enum):
    """Trading session mode."""

    RTH = "rth"  # Regular trading hours
    ETH = "eth"  # Extended trading hours
    FULL = "full"  # 24-hour


class StopMode(str, Enum):
    """Stop loss placement mode."""

    OR_OPPOSITE = "or_opposite"  # Opposite OR boundary
    SWING = "swing"  # Last swing pivot
    ATR_CAPPED = "atr_capped"  # Structural stop capped by ATR


class InstrumentConfig(BaseModel):
    """Configuration for a single instrument."""

    symbol: str = Field(..., description="Trading symbol")
    proxy_symbol: str = Field(..., description="Free data proxy symbol (e.g., SPY for ES)")
    data_source: Literal["yahoo", "binance", "alphavantage", "synthetic"] = Field(
        ..., description="Data source provider"
    )
    session_mode: SessionMode = Field(
        SessionMode.RTH, description="Trading session type"
    )
    session_start: time = Field(..., description="Session start time (local/exchange)")
    session_end: time = Field(..., description="Session end time (local/exchange)")
    timezone: str = Field("America/Chicago", description="Exchange timezone")
    tick_size: float = Field(..., description="Minimum price increment")
    point_value: float = Field(..., description="Dollar value per full point")
    enabled: bool = Field(True, description="Enable trading this instrument")

    @field_validator("symbol", "proxy_symbol")
    @classmethod
    def validate_symbol_format(cls, v: str) -> str:
        """Ensure symbols are uppercase."""
        return v.upper()


class ORBConfig(BaseModel):
    """Opening Range configuration."""

    base_minutes: int = Field(15, ge=5, le=60, description="Base OR duration (minutes)")
    adaptive: bool = Field(True, description="Use adaptive OR duration based on volatility")
    
    # Adaptive thresholds
    low_norm_vol: float = Field(
        0.35, ge=0.0, le=1.0, description="Normalized vol threshold for short OR"
    )
    high_norm_vol: float = Field(
        0.85, ge=0.0, le=2.0, description="Normalized vol threshold for long OR"
    )
    short_or_minutes: int = Field(10, ge=5, le=30, description="Short OR duration")
    long_or_minutes: int = Field(30, ge=15, le=60, description="Long OR duration")
    
    # Volatility calculation
    atr_period: int = Field(14, ge=5, le=50, description="ATR lookback period")
    intraday_atr_timeframe: str = Field("5min", description="Intraday ATR timeframe")
    daily_atr_timeframe: str = Field("1day", description="Daily ATR timeframe")
    
    # OR validity filters
    enable_validity_filter: bool = Field(True, description="Require valid OR width")
    min_atr_mult: float = Field(
        0.25, ge=0.0, description="Minimum OR width as ATR multiple"
    )
    max_atr_mult: float = Field(
        1.75, ge=0.0, description="Maximum OR width as ATR multiple"
    )

    @model_validator(mode="after")
    def validate_or_thresholds(self) -> "ORBConfig":
        """Ensure OR thresholds are sensible."""
        if self.min_atr_mult >= self.max_atr_mult:
            raise ValueError("min_atr_mult must be < max_atr_mult")
        if self.low_norm_vol >= self.high_norm_vol:
            raise ValueError("low_norm_vol must be < high_norm_vol")
        if self.short_or_minutes >= self.long_or_minutes:
            raise ValueError("short_or_minutes must be < long_or_minutes")
        return self


class BuffersConfig(BaseModel):
    """Breakout buffer configuration."""

    fixed: float = Field(0.0, ge=0.0, description="Fixed buffer (instrument-specific units)")
    use_atr: bool = Field(False, description="Add ATR-based dynamic buffer")
    atr_mult: float = Field(0.05, ge=0.0, le=0.5, description="ATR buffer multiplier")


class RelativeVolumeConfig(BaseModel):
    """Relative volume factor configuration."""

    enabled: bool = Field(True, description="Enable relative volume factor")
    lookback: int = Field(20, ge=5, le=100, description="Volume SMA lookback periods")
    spike_mult: float = Field(1.25, ge=1.0, description="Spike threshold multiplier")


class PriceActionConfig(BaseModel):
    """Price action pattern factor configuration."""

    enabled: bool = Field(True, description="Enable price action factor")
    pivot_len: int = Field(3, ge=2, le=10, description="Pivot lookback length")
    enable_engulfing: bool = Field(True, description="Check for engulfing patterns")
    enable_structure: bool = Field(True, description="Check for HH/HL or LL/LH structure")


class ProfileProxyConfig(BaseModel):
    """Profile proxy factor configuration."""

    enabled: bool = Field(True, description="Enable profile proxy factor")
    val_pct: float = Field(0.25, ge=0.0, le=1.0, description="Value Area Low percentile")
    vah_pct: float = Field(0.75, ge=0.0, le=1.0, description="Value Area High percentile")


class VWAPConfig(BaseModel):
    """VWAP factor configuration."""

    enabled: bool = Field(False, description="Enable VWAP factor")
    reset_mode: Literal["session", "or_end"] = Field(
        "session", description="VWAP reset point"
    )


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


class ScoringConfig(BaseModel):
    """Confluence scoring configuration."""

    enabled: bool = Field(True, description="Enable confluence scoring gate")
    base_required: int = Field(3, ge=0, le=10, description="Base score required for entry")
    weak_trend_required: int = Field(
        4, ge=0, le=10, description="Score required in weak trend (ADX < threshold)"
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


class TradeConfig(BaseModel):
    """Trade execution and management configuration."""

    # Stop placement
    stop_mode: StopMode = Field(StopMode.OR_OPPOSITE, description="Stop placement mode")
    extra_stop_buffer: float = Field(
        0.0, ge=0.0, description="Extra buffer beyond structural stop"
    )
    atr_stop_cap_mult: float = Field(
        0.80, ge=0.0, description="ATR cap multiplier for stop distance"
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
    be_buffer: float = Field(
        0.0, ge=0.0, description="Buffer when moving to breakeven (ticks)"
    )

    @model_validator(mode="after")
    def validate_trade_params(self) -> "TradeConfig":
        """Ensure trade parameters are sensible."""
        if self.partials:
            if self.t1_pct + self.t2_pct > 1.0:
                raise ValueError("t1_pct + t2_pct must be <= 1.0")
            if self.t1_r >= self.t2_r:
                raise ValueError("t1_r must be < t2_r")
            if self.t2_r >= self.runner_r:
                raise ValueError("t2_r must be < runner_r")
        return self


class GovernanceConfig(BaseModel):
    """Risk governance and discipline configuration."""

    max_signals_per_day: int = Field(
        3, ge=1, le=10, description="Maximum signals per instrument per day"
    )
    lockout_after_losses: int = Field(
        2, ge=1, le=10, description="Consecutive full-stop losses before lockout"
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
    initial_capital: float = Field(100000.0, gt=0.0, description="Initial capital (for sizing)")
    contracts_per_trade: int = Field(1, ge=1, description="Contracts per trade (fixed)")
    
    # Fill model
    conservative_fills: bool = Field(
        True,
        description="If stop & target both hit in bar, assume stop first",
    )
    
    # Determinism
    random_seed: int = Field(42, description="Random seed for reproducibility")
    
    # Outputs
    output_dir: Path = Field(Path("runs"), description="Output directory for results")
    save_factor_matrix: bool = Field(True, description="Save full factor matrix")
    save_trades: bool = Field(True, description="Save trade log")
    save_equity_curve: bool = Field(True, description="Save equity curve")


class StrategyConfig(BaseModel):
    """Root strategy configuration."""

    name: str = Field("ORB_Confluence", description="Strategy name")
    version: str = Field("1.0", description="Configuration version")
    
    instruments: Dict[str, InstrumentConfig] = Field(
        ..., description="Instrument configurations"
    )
    orb: ORBConfig = Field(default_factory=ORBConfig)
    buffers: BuffersConfig = Field(default_factory=BuffersConfig)
    factors: FactorsConfig = Field(default_factory=FactorsConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    trade: TradeConfig = Field(default_factory=TradeConfig)
    governance: GovernanceConfig = Field(default_factory=GovernanceConfig)
    backtest: BacktestConfig = Field(..., description="Backtest parameters")
    
    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        "INFO", description="Logging level"
    )
    log_to_file: bool = Field(True, description="Write logs to file")

    @model_validator(mode="after")
    def validate_strategy(self) -> "StrategyConfig":
        """Cross-field validation."""
        # Ensure at least one instrument is enabled
        if not any(inst.enabled for inst in self.instruments.values()):
            raise ValueError("At least one instrument must be enabled")
        return self


def load_config(path: Path | str) -> StrategyConfig:
    """Load and validate strategy configuration from YAML.

    Args:
        path: Path to YAML configuration file.

    Returns:
        Validated StrategyConfig instance.

    Raises:
        FileNotFoundError: If config file doesn't exist.
        ValueError: If config validation fails.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    yaml = YAML(typ="safe")
    with path.open("r") as f:
        raw_config = yaml.load(f)

    try:
        config = StrategyConfig(**raw_config)
    except Exception as e:
        raise ValueError(f"Config validation failed: {e}") from e

    return config
