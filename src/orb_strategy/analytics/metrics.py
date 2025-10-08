"""Performance analytics and metrics computation."""

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from loguru import logger

from ..backtest.engine import BacktestResult
from ..execution.position import Position


class PerformanceAnalyzer:
    """Analyzes backtest results and computes advanced metrics.

    Provides:
    - Factor attribution analysis
    - Drawdown analysis
    - R distribution statistics
    - Win/loss analysis by time/conditions
    """

    def __init__(self, result: BacktestResult) -> None:
        """Initialize performance analyzer.

        Args:
            result: Backtest result to analyze.
        """
        self.result = result
        self.trades = result.trades

    def factor_attribution(self) -> pd.DataFrame:
        """Analyze performance by factor presence.

        Returns:
            DataFrame with factor name, trades with factor, avg R, win rate.
        """
        if not self.trades:
            return pd.DataFrame(columns=["factor", "count", "avg_r", "win_rate"])

        # Extract factor signals from trades
        factor_names = set()
        for trade in self.trades:
            if trade.factor_signals:
                factor_names.update(trade.factor_signals.keys())

        attribution_data = []

        for factor_name in sorted(factor_names):
            # Filter trades where this factor was active (long or short)
            relevant_trades = []

            for trade in self.trades:
                if factor_name in trade.factor_signals:
                    factor_sig = trade.factor_signals[factor_name]
                    
                    # Check if factor fired for trade direction
                    if trade.direction.value == "long" and factor_sig.get("long", False):
                        relevant_trades.append(trade)
                    elif trade.direction.value == "short" and factor_sig.get("short", False):
                        relevant_trades.append(trade)

            if relevant_trades:
                r_values = [t.realized_r for t in relevant_trades]
                wins = sum(1 for r in r_values if r > 0)
                
                attribution_data.append({
                    "factor": factor_name,
                    "count": len(relevant_trades),
                    "avg_r": np.mean(r_values),
                    "win_rate": wins / len(relevant_trades),
                    "total_r": np.sum(r_values),
                })

        df = pd.DataFrame(attribution_data)
        return df.sort_values("avg_r", ascending=False) if not df.empty else df

    def score_tier_analysis(self) -> pd.DataFrame:
        """Analyze performance by confluence score tiers.

        Returns:
            DataFrame with score tier, count, avg R, win rate.
        """
        if not self.trades:
            return pd.DataFrame(columns=["score_tier", "count", "avg_r", "win_rate"])

        tier_data = []

        # Define score tiers
        tiers = [(0, 2), (2, 3), (3, 4), (4, 100)]

        for tier_min, tier_max in tiers:
            tier_name = f"{tier_min}-{tier_max}" if tier_max < 100 else f"{tier_min}+"

            # Filter trades in this tier
            tier_trades = []
            for trade in self.trades:
                if trade.direction.value == "long":
                    score = trade.confluence_score_long
                else:
                    score = trade.confluence_score_short

                if tier_min <= score < tier_max:
                    tier_trades.append(trade)

            if tier_trades:
                r_values = [t.realized_r for t in tier_trades]
                wins = sum(1 for r in r_values if r > 0)

                tier_data.append({
                    "score_tier": tier_name,
                    "count": len(tier_trades),
                    "avg_r": np.mean(r_values),
                    "win_rate": wins / len(tier_trades),
                    "total_r": np.sum(r_values),
                })

        return pd.DataFrame(tier_data)

    def drawdown_analysis(self) -> Dict[str, float]:
        """Compute drawdown statistics from equity curve.

        Returns:
            Dict with max_drawdown_r, max_drawdown_pct, recovery_time_days.
        """
        if self.result.equity_curve is None or self.result.equity_curve.empty:
            return {
                "max_drawdown_r": 0.0,
                "max_drawdown_pct": 0.0,
                "longest_drawdown_days": 0,
            }

        equity = self.result.equity_curve["cumulative_r"].values

        # Compute running maximum
        running_max = np.maximum.accumulate(equity)

        # Drawdown at each point
        drawdown = equity - running_max

        max_dd = np.min(drawdown)
        max_dd_pct = max_dd / running_max[np.argmin(drawdown)] if running_max[np.argmin(drawdown)] != 0 else 0.0

        # Find longest drawdown period
        in_dd = drawdown < 0
        dd_periods = []
        start_idx = None

        for i, is_dd in enumerate(in_dd):
            if is_dd and start_idx is None:
                start_idx = i
            elif not is_dd and start_idx is not None:
                dd_periods.append((start_idx, i - 1))
                start_idx = None

        if start_idx is not None:
            dd_periods.append((start_idx, len(in_dd) - 1))

        longest_dd_days = 0
        if dd_periods:
            longest_dd_bars = max(end - start for start, end in dd_periods)
            # Estimate days (simplified)
            longest_dd_days = longest_dd_bars  # Would need actual date range

        return {
            "max_drawdown_r": max_dd,
            "max_drawdown_pct": max_dd_pct,
            "longest_drawdown_days": longest_dd_days,
        }

    def or_validity_impact(self) -> Dict[str, Dict[str, float]]:
        """Analyze performance difference between valid and invalid ORs.

        Returns:
            Dict with valid/invalid statistics.
        """
        valid_trades = [t for t in self.trades if t.or_valid]
        invalid_trades = [t for t in self.trades if not t.or_valid]

        def compute_stats(trades: List[Position]) -> Dict[str, float]:
            if not trades:
                return {"count": 0, "avg_r": 0.0, "win_rate": 0.0}

            r_values = [t.realized_r for t in trades]
            wins = sum(1 for r in r_values if r > 0)

            return {
                "count": len(trades),
                "avg_r": np.mean(r_values),
                "win_rate": wins / len(trades),
                "total_r": np.sum(r_values),
            }

        return {
            "valid_or": compute_stats(valid_trades),
            "invalid_or": compute_stats(invalid_trades),
        }

    def time_of_day_analysis(self) -> pd.DataFrame:
        """Analyze performance by entry hour.

        Returns:
            DataFrame with hour, count, avg R, win rate.
        """
        if not self.trades:
            return pd.DataFrame(columns=["hour", "count", "avg_r", "win_rate"])

        hour_data = {}

        for trade in self.trades:
            hour = trade.entry_time.hour

            if hour not in hour_data:
                hour_data[hour] = []

            hour_data[hour].append(trade.realized_r)

        results = []
        for hour, r_values in sorted(hour_data.items()):
            wins = sum(1 for r in r_values if r > 0)

            results.append({
                "hour": hour,
                "count": len(r_values),
                "avg_r": np.mean(r_values),
                "win_rate": wins / len(r_values),
                "total_r": np.sum(r_values),
            })

        return pd.DataFrame(results)
