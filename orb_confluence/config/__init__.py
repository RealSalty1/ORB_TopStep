"""Configuration management for ORB strategy.

Handles loading, validation, merging, and hashing of strategy parameters.
"""

from .schema import (
    StrategyConfig,
    InstrumentConfig,
    ORBConfig,
    BuffersConfig,
    FactorsConfig,
    ScoringConfig,
    TradeConfig,
    GovernanceConfig,
    BacktestConfig,
    OptimizationConfig,
    RelativeVolumeConfig,
    PriceActionConfig,
    ProfileProxyConfig,
    VWAPConfig,
    ADXConfig,
    SessionMode,
    StopMode,
)
from .loader import (
    load_config,
    get_default_config,
    resolved_config_hash,
    save_config,
    deep_merge,
)

__all__ = [
    # Main config
    "StrategyConfig",
    # Component configs
    "InstrumentConfig",
    "ORBConfig",
    "BuffersConfig",
    "FactorsConfig",
    "ScoringConfig",
    "TradeConfig",
    "GovernanceConfig",
    "BacktestConfig",
    "OptimizationConfig",
    # Factor configs
    "RelativeVolumeConfig",
    "PriceActionConfig",
    "ProfileProxyConfig",
    "VWAPConfig",
    "ADXConfig",
    # Enums
    "SessionMode",
    "StopMode",
    # Loaders
    "load_config",
    "get_default_config",
    "resolved_config_hash",
    "save_config",
    "deep_merge",
]