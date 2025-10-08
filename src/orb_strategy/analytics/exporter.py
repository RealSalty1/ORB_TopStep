"""Result exporter for saving backtest artifacts."""

from pathlib import Path
from typing import Optional

import pandas as pd
from loguru import logger

from ..backtest.engine import BacktestResult


class ResultExporter:
    """Exports backtest results to various formats.

    Saves:
    - Trades log (Parquet/CSV)
    - Equity curve (Parquet/CSV)
    - Opening ranges (Parquet/CSV)
    - Configuration snapshot (YAML)
    """

    def __init__(self, output_dir: Path) -> None:
        """Initialize result exporter.

        Args:
            output_dir: Base output directory.
        """
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_result(
        self,
        result: BacktestResult,
        save_trades: bool = True,
        save_equity: bool = True,
        save_ors: bool = True,
    ) -> Path:
        """Export backtest result to files.

        Args:
            result: Backtest result to export.
            save_trades: Save trades log.
            save_equity: Save equity curve.
            save_ors: Save opening ranges.

        Returns:
            Path to run directory.
        """
        run_dir = self.output_dir / result.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Exporting backtest results to {run_dir}")

        # Export trades
        if save_trades and result.trades:
            trades_path = run_dir / "trades.parquet"
            trades_df = self._trades_to_dataframe(result.trades)
            trades_df.to_parquet(trades_path, compression="snappy")
            logger.info(f"Saved {len(trades_df)} trades to {trades_path}")

        # Export equity curve
        if save_equity and result.equity_curve is not None:
            equity_path = run_dir / "equity_curve.parquet"
            result.equity_curve.to_parquet(equity_path, compression="snappy")
            logger.info(f"Saved equity curve to {equity_path}")

        # Export opening ranges
        if save_ors and result.opening_ranges:
            ors_path = run_dir / "opening_ranges.parquet"
            ors_df = self._ors_to_dataframe(result.opening_ranges)
            ors_df.to_parquet(ors_path, compression="snappy")
            logger.info(f"Saved {len(ors_df)} opening ranges to {ors_path}")

        # Export summary metrics
        metrics_path = run_dir / "metrics.json"
        metrics = self._extract_metrics(result)
        
        import json
        with metrics_path.open("w") as f:
            json.dump(metrics, f, indent=2, default=str)
        
        logger.info(f"Saved metrics to {metrics_path}")

        return run_dir

    @staticmethod
    def _trades_to_dataframe(trades) -> pd.DataFrame:
        """Convert trades to DataFrame.

        Args:
            trades: List of Position objects.

        Returns:
            DataFrame with trade data.
        """
        return pd.DataFrame([t.to_dict() for t in trades])

    @staticmethod
    def _ors_to_dataframe(opening_ranges) -> pd.DataFrame:
        """Convert opening ranges to DataFrame.

        Args:
            opening_ranges: List of OpeningRange objects.

        Returns:
            DataFrame with OR data.
        """
        data = []
        for or_obj in opening_ranges:
            data.append({
                "symbol": or_obj.symbol,
                "date": or_obj.date,
                "start_time": or_obj.start_time,
                "end_time": or_obj.end_time,
                "duration_minutes": or_obj.duration_minutes,
                "or_high": or_obj.or_high,
                "or_low": or_obj.or_low,
                "or_width": or_obj.or_width,
                "validity": or_obj.validity.value,
                "invalid_reason": or_obj.invalid_reason,
                "atr_value": or_obj.atr_value,
                "normalized_vol": or_obj.normalized_vol,
            })

        return pd.DataFrame(data)

    @staticmethod
    def _extract_metrics(result: BacktestResult) -> dict:
        """Extract summary metrics to dict.

        Args:
            result: Backtest result.

        Returns:
            Dict with metrics.
        """
        return {
            "run_id": result.run_id,
            "total_trades": result.total_trades,
            "winning_trades": result.winning_trades,
            "losing_trades": result.losing_trades,
            "win_rate": result.win_rate,
            "avg_r": result.avg_r,
            "total_r": result.total_r,
            "max_r": result.max_r,
            "min_r": result.min_r,
            "expectancy": result.expectancy,
            "profit_factor": result.profit_factor,
            "max_consecutive_wins": result.max_consecutive_wins,
            "max_consecutive_losses": result.max_consecutive_losses,
            "or_valid_count": result.or_valid_count,
            "or_invalid_count": result.or_invalid_count,
            "signals_blocked_by_governance": result.signals_blocked_by_governance,
            "start_time": str(result.start_time),
            "end_time": str(result.end_time),
        }
