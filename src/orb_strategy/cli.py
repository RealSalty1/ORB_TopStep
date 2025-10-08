"""Command-line interface for running backtests."""

import argparse
import sys
from pathlib import Path

from loguru import logger

from .config import load_config
from .data import DataManager
from .backtest import BacktestEngine
from .analytics import ResultExporter, PerformanceAnalyzer
from .reporting import HTMLReportGenerator
from .utils import setup_logger


def main() -> int:
    """Main CLI entry point.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    parser = argparse.ArgumentParser(
        description="ORB Confluence Breakout Strategy Backtester"
    )
    
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        required=True,
        help="Path to strategy configuration YAML file",
    )
    
    parser.add_argument(
        "--report",
        "-r",
        action="store_true",
        help="Generate HTML report",
    )
    
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=None,
        help="Override output directory (default from config)",
    )
    
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("data/cache"),
        help="Cache directory for data storage",
    )
    
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable data caching",
    )

    args = parser.parse_args()

    # Validate config file
    if not args.config.exists():
        print(f"Error: Config file not found: {args.config}", file=sys.stderr)
        return 1

    try:
        # Load configuration
        config = load_config(args.config)
        
        # Setup logging
        setup_logger(
            log_level=config.log_level,
            log_to_file=config.log_to_file,
            log_dir=Path("logs"),
            run_id=None,
        )
        
        logger.info(f"Loaded configuration from {args.config}")
        logger.info(f"Strategy: {config.name} v{config.version}")

        # Initialize data manager
        cache_dir = args.cache_dir if not args.no_cache else Path("data/cache")
        data_manager = DataManager(
            cache_dir=cache_dir,
            enable_cache=not args.no_cache,
        )

        # Run backtest
        engine = BacktestEngine(config=config, data_manager=data_manager)
        result = engine.run()

        # Export results
        output_dir = args.output_dir or config.backtest.output_dir
        exporter = ResultExporter(output_dir)
        run_dir = exporter.export_result(
            result=result,
            save_trades=config.backtest.save_trades,
            save_equity=config.backtest.save_equity_curve,
            save_ors=True,
        )

        logger.info(f"Results exported to {run_dir}")

        # Generate HTML report
        if args.report:
            report_path = run_dir / "report.html"
            report_generator = HTMLReportGenerator()
            report_generator.generate(result, report_path)
            logger.info(f"HTML report generated: {report_path}")

        # Print summary
        print("\n" + "=" * 60)
        print("BACKTEST SUMMARY")
        print("=" * 60)
        print(f"Run ID:           {result.run_id}")
        print(f"Total Trades:     {result.total_trades}")
        print(f"Win Rate:         {result.win_rate:.1%}")
        print(f"Avg R:            {result.avg_r:.2f}")
        print(f"Total R:          {result.total_r:.2f}")
        print(f"Expectancy:       {result.expectancy:.2f}")
        print(f"Profit Factor:    {result.profit_factor:.2f}")
        print(f"Max R:            {result.max_r:.2f}")
        print(f"Min R:            {result.min_r:.2f}")
        print(f"Max Consec Wins:  {result.max_consecutive_wins}")
        print(f"Max Consec Loss:  {result.max_consecutive_losses}")
        print(f"Valid ORs:        {result.or_valid_count}/{result.or_valid_count + result.or_invalid_count}")
        print("=" * 60)
        print(f"\nResults saved to: {run_dir}")
        
        if args.report:
            print(f"Report available: {run_dir / 'report.html'}")

        return 0

    except Exception as e:
        logger.error(f"Backtest failed: {e}", exc_info=True)
        print(f"\nError: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
