"""Backtest engine modules.

Includes:
- Event loop simulation
- Fill models
- Vectorized backtest (future)
"""

from .event_loop import (
    EventLoopBacktest,
    BacktestResult,
    FactorSnapshot,
)

__all__ = [
    "EventLoopBacktest",
    "BacktestResult",
    "FactorSnapshot",
]