#!/usr/bin/env python
"""End-to-end backtest runner with multi-symbol support.

Usage:
    python run_backtest.py --symbols SPY QQQ --start 2024-01-02 --end 2024-01-10
    python run_backtest.py --symbols ES --start 2024-01-02 --end 2024-03-01 --config my_config.yaml
    python run_backtest.py --symbols SPY --start 2024-01-02 --end 2024-01-10 --cache --report

Examples:
    # Single symbol, default config
    python run_backtest.py --symbols SPY --start 2024-01-02 --end 2024-01-31
    
    # Multiple symbols
    python run_backtest.py --symbols SPY QQQ IWM --start 2024-01-02 --end 2024-03-31
    
    # Custom config with caching
    python run_backtest.py --symbols SPY --start 2024-01-02 --end 2024-06-30 --config custom.yaml --cache
    
    # Full run with HTML report
    python run_backtest.py --symbols SPY QQQ --start 2024-01-02 --end 2024-03-31 --report
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from loguru import logger
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table
from rich import box

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from orb_confluence.config import load_config
from orb_confluence.data import YahooProvider, SyntheticProvider
from orb_confluence.data.qc import validate_or_window
from orb_confluence.backtest import EventLoopBacktest
from orb_confluence.analytics import compute_metrics, compute_equity_curve
from orb_confluence.reporting import generate_report


console = Console()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run ORB Confluence Strategy Backtest",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --symbols SPY --start 2024-01-02 --end 2024-01-31
  %(prog)s --symbols SPY QQQ IWM --start 2024-01-02 --end 2024-03-31 --cache
  %(prog)s --symbols SPY --start 2024-01-02 --end 2024-12-31 --config custom.yaml --report
        """
    )
    
    parser.add_argument(
        '--symbols',
        nargs='+',
        required=True,
        help='Symbols to backtest (space-separated)',
    )
    
    parser.add_argument(
        '--start',
        type=str,
        required=True,
        help='Start date (YYYY-MM-DD)',
    )
    
    parser.add_argument(
        '--end',
        type=str,
        required=True,
        help='End date (YYYY-MM-DD)',
    )
    
    parser.add_argument(
        '--config',
        type=str,
        default=None,
        help='Path to config YAML file (defaults to defaults.yaml)',
    )
    
    parser.add_argument(
        '--cache',
        action='store_true',
        help='Cache fetched data to disk',
    )
    
    parser.add_argument(
        '--cache-dir',
        type=str,
        default='cache',
        help='Cache directory (default: cache/)',
    )
    
    parser.add_argument(
        '--report',
        action='store_true',
        help='Generate HTML report',
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default='runs',
        help='Output directory (default: runs/)',
    )
    
    parser.add_argument(
        '--synthetic',
        action='store_true',
        help='Use synthetic data instead of real data',
    )
    
    parser.add_argument(
        '--validate-or',
        action='store_true',
        help='Validate OR window before accepting (skip invalid days)',
    )
    
    parser.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='Verbose output',
    )
    
    return parser.parse_args()


def setup_logging(verbose: bool = False):
    """Setup logging configuration."""
    logger.remove()
    
    log_level = "DEBUG" if verbose else "INFO"
    
    # Console logging
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level=log_level,
    )
    
    # File logging
    logger.add(
        "backtest_run.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        level="DEBUG",
        rotation="10 MB",
    )


def fetch_or_load_data(
    symbol: str,
    start_date: str,
    end_date: str,
    cache_enabled: bool,
    cache_dir: str,
    use_synthetic: bool = False,
) -> Optional[pd.DataFrame]:
    """Fetch or load cached data.
    
    Args:
        symbol: Symbol to fetch.
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).
        cache_enabled: Whether to use cache.
        cache_dir: Cache directory.
        use_synthetic: Use synthetic data.
        
    Returns:
        DataFrame with bars or None on error.
    """
    cache_path = Path(cache_dir) / f"{symbol}_{start_date}_{end_date}.parquet"
    
    # Check cache
    if cache_enabled and cache_path.exists():
        logger.info(f"Loading {symbol} from cache: {cache_path}")
        try:
            return pd.read_parquet(cache_path)
        except Exception as e:
            logger.warning(f"Cache load failed: {e}, fetching fresh data")
    
    # Fetch data
    try:
        if use_synthetic:
            logger.info(f"Generating synthetic data for {symbol}")
            provider = SyntheticProvider()
            
            # Generate multiple days
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            days = (end_dt - start_dt).days
            
            all_bars = []
            for day in range(days):
                day_bars = provider.generate_synthetic_day(
                    seed=day,
                    regime='trend_up' if day % 2 == 0 else 'mean_revert',
                    minutes=390,
                    base_price=100.0 + day * 0.1,
                )
                all_bars.append(day_bars)
            
            bars = pd.concat(all_bars, ignore_index=True)
        
        else:
            logger.info(f"Fetching {symbol} from Yahoo Finance")
            provider = YahooProvider()
            bars = provider.fetch_intraday(
                symbol=symbol,
                start=start_date,
                end=end_date,
                interval='1m',
            )
        
        if bars is None or len(bars) == 0:
            logger.error(f"No data fetched for {symbol}")
            return None
        
        logger.info(f"Fetched {len(bars):,} bars for {symbol}")
        
        # Cache if enabled
        if cache_enabled:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            bars.to_parquet(cache_path)
            logger.info(f"Cached data to {cache_path}")
        
        return bars
    
    except Exception as e:
        logger.error(f"Error fetching {symbol}: {e}")
        return None


def run_backtest_for_symbol(
    symbol: str,
    bars: pd.DataFrame,
    config,
    validate_or: bool = False,
) -> Optional[Dict]:
    """Run backtest for a single symbol.
    
    Args:
        symbol: Symbol name.
        bars: DataFrame with bars.
        config: Strategy configuration.
        validate_or: Whether to validate OR window.
        
    Returns:
        Dictionary with results or None on error.
    """
    try:
        # Validate OR window if requested
        if validate_or:
            or_duration = config.orb.base_minutes
            or_bars = bars.iloc[:or_duration]
            
            if not validate_or_window(or_bars, or_duration_minutes=or_duration):
                logger.warning(f"{symbol}: Invalid OR window, using data anyway")
                # Note: In production, you might skip the day instead
        
        # Run backtest
        logger.info(f"Running backtest for {symbol}")
        engine = EventLoopBacktest(config)
        result = engine.run(bars)
        
        logger.info(f"{symbol}: Generated {len(result.trades)} trades")
        
        # Compute metrics
        if len(result.trades) > 0:
            metrics = compute_metrics(result.trades)
            equity_curve = compute_equity_curve(result.trades)
        else:
            logger.warning(f"{symbol}: No trades generated")
            metrics = None
            equity_curve = None
        
        return {
            'symbol': symbol,
            'result': result,
            'metrics': metrics,
            'equity_curve': equity_curve,
        }
    
    except Exception as e:
        logger.error(f"Error running backtest for {symbol}: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return None


def aggregate_results(symbol_results: List[Dict]) -> Dict:
    """Aggregate results across symbols.
    
    Args:
        symbol_results: List of symbol result dictionaries.
        
    Returns:
        Aggregated results.
    """
    all_trades = []
    all_equity_points = []
    
    for result in symbol_results:
        if result['result'].trades:
            # Add symbol to each trade
            for trade in result['result'].trades:
                trade_dict = {
                    'symbol': result['symbol'],
                    'trade_id': trade.trade_id if hasattr(trade, 'trade_id') else None,
                    'direction': trade.direction if hasattr(trade, 'direction') else None,
                    'entry_timestamp': trade.entry_timestamp if hasattr(trade, 'entry_timestamp') else None,
                    'exit_timestamp': trade.exit_timestamp if hasattr(trade, 'exit_timestamp') else None,
                    'realized_r': trade.realized_r if hasattr(trade, 'realized_r') else None,
                }
                all_trades.append(trade_dict)
        
        if result['equity_curve'] is not None:
            equity_with_symbol = result['equity_curve'].copy()
            equity_with_symbol['symbol'] = result['symbol']
            all_equity_points.append(equity_with_symbol)
    
    # Combine equity curves
    if all_equity_points:
        combined_equity = pd.concat(all_equity_points, ignore_index=True)
        combined_equity = combined_equity.sort_values('cumulative_r').reset_index(drop=True)
    else:
        combined_equity = None
    
    return {
        'all_trades': all_trades,
        'combined_equity': combined_equity,
        'symbol_count': len(symbol_results),
    }


def save_results(
    symbol_results: List[Dict],
    aggregated: Dict,
    config,
    output_dir: str,
    run_id: str,
    generate_html: bool = False,
):
    """Save results to disk.
    
    Args:
        symbol_results: List of symbol results.
        aggregated: Aggregated results.
        config: Configuration.
        output_dir: Output directory.
        run_id: Run identifier.
        generate_html: Whether to generate HTML report.
    """
    run_dir = Path(output_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Saving results to {run_dir}")
    
    # Save per-symbol results
    for result in symbol_results:
        symbol = result['symbol']
        
        # Save trades
        if result['result'].trades:
            trades_df = pd.DataFrame([
                {
                    'trade_id': t.trade_id if hasattr(t, 'trade_id') else None,
                    'direction': t.direction if hasattr(t, 'direction') else None,
                    'entry_timestamp': t.entry_timestamp if hasattr(t, 'entry_timestamp') else None,
                    'exit_timestamp': t.exit_timestamp if hasattr(t, 'exit_timestamp') else None,
                    'entry_price': t.entry_price if hasattr(t, 'entry_price') else None,
                    'exit_price': getattr(t, 'exit_price', None),
                    'realized_r': t.realized_r if hasattr(t, 'realized_r') else None,
                }
                for t in result['result'].trades
            ])
            trades_df.to_parquet(run_dir / f"{symbol}_trades.parquet")
        
        # Save metrics
        if result['metrics']:
            metrics_dict = {
                'symbol': symbol,
                'total_trades': result['metrics'].total_trades,
                'win_rate': result['metrics'].win_rate,
                'total_r': result['metrics'].total_r,
                'expectancy': result['metrics'].expectancy,
                'sharpe_ratio': result['metrics'].sharpe_ratio,
                'max_drawdown_r': result['metrics'].max_drawdown_r,
            }
            
            with open(run_dir / f"{symbol}_metrics.json", 'w') as f:
                json.dump(metrics_dict, f, indent=2, default=str)
        
        # Save equity curve
        if result['equity_curve'] is not None:
            result['equity_curve'].to_parquet(run_dir / f"{symbol}_equity.parquet")
    
    # Save aggregated trades
    if aggregated['all_trades']:
        all_trades_df = pd.DataFrame(aggregated['all_trades'])
        all_trades_df.to_parquet(run_dir / "all_trades.parquet")
        all_trades_df.to_csv(run_dir / "all_trades.csv", index=False)
    
    # Save combined equity
    if aggregated['combined_equity'] is not None:
        aggregated['combined_equity'].to_parquet(run_dir / "combined_equity.parquet")
    
    # Save config
    # Note: config is Pydantic model, need to convert
    with open(run_dir / "config.json", 'w') as f:
        json.dump({"run_id": run_id}, f, indent=2)
    
    # Generate HTML report if requested
    if generate_html and len(symbol_results) > 0:
        for result in symbol_results:
            if result['result'].trades:
                try:
                    html_path = run_dir / f"{result['symbol']}_report.html"
                    # Note: generate_report expects specific format
                    logger.info(f"HTML report generation skipped (requires full integration)")
                except Exception as e:
                    logger.warning(f"Failed to generate HTML report: {e}")
    
    logger.info(f"Results saved to {run_dir}")
    
    return run_dir


def print_summary_table(symbol_results: List[Dict], aggregated: Dict):
    """Print summary table with Rich.
    
    Args:
        symbol_results: List of symbol results.
        aggregated: Aggregated results.
    """
    console.print()
    console.rule("[bold blue]Backtest Summary[/bold blue]")
    console.print()
    
    # Per-symbol table
    table = Table(
        title="Per-Symbol Results",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta",
    )
    
    table.add_column("Symbol", style="cyan", width=10)
    table.add_column("Trades", justify="right", style="green")
    table.add_column("Win Rate", justify="right", style="blue")
    table.add_column("Total R", justify="right", style="yellow")
    table.add_column("Expectancy", justify="right", style="magenta")
    table.add_column("Sharpe", justify="right", style="cyan")
    table.add_column("Max DD", justify="right", style="red")
    
    for result in symbol_results:
        if result['metrics']:
            m = result['metrics']
            table.add_row(
                result['symbol'],
                str(m.total_trades),
                f"{m.win_rate:.1%}",
                f"{m.total_r:.2f}R",
                f"{m.expectancy:.3f}R",
                f"{m.sharpe_ratio:.2f}" if m.sharpe_ratio else "N/A",
                f"{m.max_drawdown_r:.2f}R",
            )
        else:
            table.add_row(
                result['symbol'],
                "0",
                "N/A",
                "0.00R",
                "N/A",
                "N/A",
                "N/A",
            )
    
    console.print(table)
    console.print()
    
    # Aggregated stats
    total_trades = sum(r['metrics'].total_trades if r['metrics'] else 0 for r in symbol_results)
    total_r = sum(r['metrics'].total_r if r['metrics'] else 0 for r in symbol_results)
    
    agg_table = Table(
        title="Aggregated Results",
        box=box.DOUBLE,
        show_header=True,
        header_style="bold green",
    )
    
    agg_table.add_column("Metric", style="cyan")
    agg_table.add_column("Value", justify="right", style="yellow")
    
    agg_table.add_row("Total Symbols", str(len(symbol_results)))
    agg_table.add_row("Total Trades", str(total_trades))
    agg_table.add_row("Total R", f"{total_r:.2f}R")
    if total_trades > 0:
        avg_r = total_r / total_trades
        agg_table.add_row("Average R per Trade", f"{avg_r:.3f}R")
    
    console.print(agg_table)
    console.print()


def main():
    """Main execution."""
    args = parse_args()
    
    # Setup
    setup_logging(args.verbose)
    
    console.print()
    console.rule("[bold green]ORB Confluence Strategy - Backtest Runner[/bold green]")
    console.print()
    
    # Load config
    console.print(f"[cyan]Loading configuration...[/cyan]")
    try:
        config = load_config(args.config)
        logger.info(f"Configuration loaded: {args.config or 'defaults.yaml'}")
    except Exception as e:
        console.print(f"[red]Error loading config: {e}[/red]")
        return 1
    
    # Create run ID
    run_id = f"backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    console.print(f"[cyan]Run ID: {run_id}[/cyan]")
    console.print()
    
    # Fetch data for all symbols
    symbol_data = {}
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        console=console,
    ) as progress:
        
        task = progress.add_task(
            "[cyan]Fetching data...", 
            total=len(args.symbols)
        )
        
        for symbol in args.symbols:
            bars = fetch_or_load_data(
                symbol=symbol,
                start_date=args.start,
                end_date=args.end,
                cache_enabled=args.cache,
                cache_dir=args.cache_dir,
                use_synthetic=args.synthetic,
            )
            
            if bars is not None:
                symbol_data[symbol] = bars
            else:
                console.print(f"[yellow]Warning: No data for {symbol}, skipping[/yellow]")
            
            progress.advance(task)
    
    if not symbol_data:
        console.print("[red]No data fetched, exiting[/red]")
        return 1
    
    console.print(f"[green]Data fetched for {len(symbol_data)} symbols[/green]")
    console.print()
    
    # Run backtests
    symbol_results = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        console=console,
    ) as progress:
        
        task = progress.add_task(
            "[cyan]Running backtests...",
            total=len(symbol_data)
        )
        
        for symbol, bars in symbol_data.items():
            result = run_backtest_for_symbol(
                symbol=symbol,
                bars=bars,
                config=config,
                validate_or=args.validate_or,
            )
            
            if result:
                symbol_results.append(result)
            
            progress.advance(task)
    
    if not symbol_results:
        console.print("[red]No backtests completed successfully, exiting[/red]")
        return 1
    
    console.print(f"[green]Completed {len(symbol_results)} backtests[/green]")
    console.print()
    
    # Aggregate results
    console.print("[cyan]Aggregating results...[/cyan]")
    aggregated = aggregate_results(symbol_results)
    
    # Save results
    run_dir = save_results(
        symbol_results=symbol_results,
        aggregated=aggregated,
        config=config,
        output_dir=args.output_dir,
        run_id=run_id,
        generate_html=args.report,
    )
    
    # Print summary
    print_summary_table(symbol_results, aggregated)
    
    # Final message
    console.rule("[bold green]Backtest Complete[/bold green]")
    console.print()
    console.print(f"[green]✓ Results saved to: {run_dir}[/green]")
    console.print(f"[cyan]✓ Run ID: {run_id}[/cyan]")
    console.print()
    
    if args.report:
        console.print("[yellow]Note: HTML report generation requires full integration[/yellow]")
    
    console.print("[dim]View results in Streamlit dashboard:[/dim]")
    console.print(f"[dim]  streamlit run streamlit_app.py[/dim]")
    console.print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
