"""Pytest configuration and fixtures."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


@pytest.fixture
def sample_bars():
    """Generate sample bar data for testing."""
    dates = pd.date_range("2024-01-01 09:30", periods=390, freq="1min", tz="UTC")
    
    df = pd.DataFrame({
        "open": np.random.uniform(100, 101, 390),
        "high": np.random.uniform(101, 102, 390),
        "low": np.random.uniform(99, 100, 390),
        "close": np.random.uniform(100, 101, 390),
        "volume": np.random.uniform(1000, 2000, 390),
    }, index=dates)
    
    # Ensure OHLC validity
    df["high"] = df[["open", "high", "close"]].max(axis=1)
    df["low"] = df[["open", "low", "close"]].min(axis=1)
    
    return df


@pytest.fixture
def sample_config():
    """Generate sample configuration."""
    from orb_confluence.config import StrategyConfig, InstrumentConfig, BacktestConfig
    from datetime import time
    
    return StrategyConfig(
        name="Test",
        instruments={
            "TEST": InstrumentConfig(
                symbol="TEST",
                proxy_symbol="TEST",
                data_source="synthetic",
                session_start=time(9, 30),
                session_end=time(16, 0),
                tick_size=0.01,
                point_value=1.0,
            )
        },
        backtest=BacktestConfig(
            start_date="2024-01-01",
            end_date="2024-01-31",
        ),
    )
