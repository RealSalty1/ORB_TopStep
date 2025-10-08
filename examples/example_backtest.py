"""Example backtest script demonstrating programmatic usage.

Run this script to see how to use the ORB strategy platform programmatically.
"""

from pathlib import Path
import sys

# Add src to path if running directly
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd
from orb_strategy.config import load_config
from orb_strategy.data import DataManager
from orb_strategy.backtest import BacktestEngine
from orb_strategy.analytics import PerformanceAnalyzer, ResultExporter
from orb_strategy.reporting import HTMLReportGenerator


def main():
    """Run example backtest."""
    print("=" * 60)
    print("ORB Strategy Example Backtest")
    print("=" * 60)

    # 1. Load configuration
    config_path = Path(__file__).parent.parent / "config" / "default.yaml"
    config = load_config(config_path)

    print(f"\nStrategy: {config.name} v{config.version}")
    print(f"Date range: {config.backtest.start_date} to {config.backtest.end_date}")
    print(f"Instruments: {list(config.instruments.keys())}")

    # 2. Run backtest
    print("\nRunning backtest...")
    data_manager = DataManager(enable_cache=True)
    engine = BacktestEngine(config=config, data_manager=data_manager)

    result = engine.run()

    # 3. Display summary
    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    print(f"Run ID:             {result.run_id}")
    print(f"Total Trades:       {result.total_trades}")
    print(f"Winning Trades:     {result.winning_trades}")
    print(f"Losing Trades:      {result.losing_trades}")
    print(f"Win Rate:           {result.win_rate:.1%}")
    print(f"Avg R:              {result.avg_r:.2f}")
    print(f"Total R:            {result.total_r:.2f}")
    print(f"Expectancy:         {result.expectancy:.2f}")
    print(f"Profit Factor:      {result.profit_factor:.2f}")
    print(f"Max R:              {result.max_r:.2f}")
    print(f"Min R:              {result.min_r:.2f}")
    print(f"Max Consec Wins:    {result.max_consecutive_wins}")
    print(f"Max Consec Losses:  {result.max_consecutive_losses}")

    # 4. Analyze with PerformanceAnalyzer
    print("\n" + "=" * 60)
    print("FACTOR ATTRIBUTION")
    print("=" * 60)

    analyzer = PerformanceAnalyzer(result)

    factor_attr = analyzer.factor_attribution()
    if not factor_attr.empty:
        print(factor_attr.to_string())
    else:
        print("No factor attribution available")

    # 5. Score tier analysis
    print("\n" + "=" * 60)
    print("SCORE TIER ANALYSIS")
    print("=" * 60)

    score_tiers = analyzer.score_tier_analysis()
    if not score_tiers.empty:
        print(score_tiers.to_string())
    else:
        print("No score tier data available")

    # 6. Drawdown analysis
    print("\n" + "=" * 60)
    print("DRAWDOWN ANALYSIS")
    print("=" * 60)

    dd_stats = analyzer.drawdown_analysis()
    print(f"Max Drawdown (R):   {dd_stats['max_drawdown_r']:.2f}")
    print(f"Max Drawdown (%):   {dd_stats['max_drawdown_pct']:.1%}")
    print(f"Longest DD Period:  {dd_stats['longest_drawdown_days']} bars")

    # 7. Export results
    print("\n" + "=" * 60)
    print("EXPORTING RESULTS")
    print("=" * 60)

    output_dir = Path(__file__).parent.parent / "runs"
    exporter = ResultExporter(output_dir)
    run_dir = exporter.export_result(result)

    print(f"Results saved to: {run_dir}")

    # 8. Generate HTML report
    report_path = run_dir / "report.html"
    report_gen = HTMLReportGenerator()
    report_gen.generate(result, report_path)

    print(f"HTML report: {report_path}")

    # 9. Show sample trades
    if result.trades:
        print("\n" + "=" * 60)
        print("SAMPLE TRADES (First 5)")
        print("=" * 60)

        trades_df = pd.DataFrame([t.to_dict() for t in result.trades[:5]])
        print(trades_df[["entry_time", "direction", "entry_price", "realized_r"]].to_string())

    print("\n" + "=" * 60)
    print("Example complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
