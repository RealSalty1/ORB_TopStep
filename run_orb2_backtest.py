#!/usr/bin/env python3
"""Run ORB 2.0 integrated backtest.

This script demonstrates the full ORB 2.0 system with:
- Dual OR layers (micro + adaptive primary)
- Auction state classification
- Multi-playbook tactics
- Two-phase stops & salvage
- Context exclusion (optional)
- Probability gating (optional)
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from loguru import logger
from rich.console import Console
from rich.table import Table
from rich import box

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from orb_confluence.backtest.orb_2_engine import ORB2Engine, ORB2Config
from orb_confluence.data import YahooProvider, SyntheticProvider
from orb_confluence.data.databento_loader import DatabentoLoader


console = Console()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run ORB 2.0 Integrated Backtest",
    )
    
    parser.add_argument(
        '--symbol',
        type=str,
        default='SPY',
        help='Symbol to backtest',
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
        '--synthetic',
        action='store_true',
        help='Use synthetic data',
    )
    
    parser.add_argument(
        '--databento',
        action='store_true',
        help='Use Databento data (for futures)',
    )
    
    parser.add_argument(
        '--databento-dir',
        type=str,
        default='data_cache/databento_1m',
        help='Databento data directory (default: data_cache/databento_1m)',
    )
    
    parser.add_argument(
        '--disable-pb1',
        action='store_true',
        help='Disable PB1 (ORB Refined)',
    )
    
    parser.add_argument(
        '--disable-pb2',
        action='store_true',
        help='Disable PB2 (Failure Fade)',
    )
    
    parser.add_argument(
        '--disable-pb3',
        action='store_true',
        help='Disable PB3 (Pullback Continuation)',
    )
    
    parser.add_argument(
        '--disable-salvage',
        action='store_true',
        help='Disable salvage abort',
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default='runs',
        help='Output directory',
    )
    
    parser.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='Verbose output',
    )
    
    return parser.parse_args()


def setup_logging(verbose: bool = False):
    """Setup logging."""
    logger.remove()
    
    log_level = "DEBUG" if verbose else "INFO"
    
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level=log_level,
    )
    
    logger.add(
        "orb2_backtest.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        level="DEBUG",
        rotation="10 MB",
    )


def fetch_data(symbol: str, start_date: str, end_date: str, use_synthetic: bool, use_databento: bool = False, databento_dir: str = None):
    """Fetch bar data."""
    if use_databento:
        logger.info(f"Loading {symbol} from Databento: {databento_dir}")
        try:
            loader = DatabentoLoader(databento_dir)
            bars = loader.load(symbol, start_date=start_date, end_date=end_date)
            
            if bars is None or len(bars) == 0:
                logger.error(f"No Databento data for {symbol}")
                return None
            
            logger.info(f"Loaded {len(bars):,} bars from Databento")
            return bars
        except Exception as e:
            logger.error(f"Error loading Databento data: {e}")
            return None
    
    elif use_synthetic:
        logger.info(f"Generating synthetic data for {symbol}")
        provider = SyntheticProvider()
        
        # Generate multiple days
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        days = (end_dt - start_dt).days
        
        all_bars = []
        for day in range(min(days, 5)):  # Limit to 5 days for testing
            day_bars = provider.generate_synthetic_day(
                seed=day + 100,
                regime='trend_up' if day % 2 == 0 else 'mean_revert',
                minutes=390,
                base_price=5000.0 + day * 10,
            )
            all_bars.append(day_bars)
        
        bars = pd.concat(all_bars, ignore_index=True)
        logger.info(f"Generated {len(bars)} synthetic bars")
    
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
        
        logger.info(f"Fetched {len(bars):,} bars")
    
    return bars


def print_results_table(results: dict):
    """Print results table."""
    console.print()
    console.rule("[bold blue]ORB 2.0 Backtest Results[/bold blue]")
    console.print()
    
    # Main metrics
    table = Table(
        title="Performance Metrics",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta",
    )
    
    table.add_column("Metric", style="cyan", width=20)
    table.add_column("Value", justify="right", style="yellow")
    
    table.add_row("Total Trades", str(results['total_trades']))
    table.add_row("Winners", str(results['winning_trades']))
    table.add_row("Losers", str(results['losing_trades']))
    table.add_row("Win Rate", f"{results['win_rate']:.1%}")
    table.add_row("", "")  # Spacer
    table.add_row("Expectancy", f"{results['expectancy']:.3f}R")
    table.add_row("Total R", f"{results['cumulative_r']:.2f}R")
    table.add_row("Avg Winner", f"+{results['avg_winner']:.2f}R")
    table.add_row("Avg Loser", f"{results['avg_loser']:.2f}R")
    table.add_row("", "")
    table.add_row("Max Win", f"+{results['max_win']:.2f}R")
    table.add_row("Max Loss", f"{results['max_loss']:.2f}R")
    table.add_row("", "")
    table.add_row("Avg MFE", f"{results['avg_mfe']:.2f}R")
    table.add_row("Avg MAE", f"{results['avg_mae']:.2f}R")
    table.add_row("Salvages", str(results['salvage_count']))
    
    console.print(table)
    console.print()
    
    # Playbook breakdown
    if results['trades_by_playbook']:
        pb_table = Table(
            title="Trades by Playbook",
            box=box.SIMPLE,
            show_header=True,
            header_style="bold green",
        )
        
        pb_table.add_column("Playbook", style="cyan")
        pb_table.add_column("Trades", justify="right", style="yellow")
        pb_table.add_column("Percentage", justify="right", style="blue")
        
        for playbook, count in results['trades_by_playbook'].items():
            pct = count / results['total_trades'] if results['total_trades'] > 0 else 0
            pb_table.add_row(playbook, str(count), f"{pct:.1%}")
        
        console.print(pb_table)
        console.print()
    
    # State breakdown
    if results['trades_by_state']:
        state_table = Table(
            title="Trades by Auction State",
            box=box.SIMPLE,
            show_header=True,
            header_style="bold green",
        )
        
        state_table.add_column("State", style="cyan")
        state_table.add_column("Trades", justify="right", style="yellow")
        
        for state, count in results['trades_by_state'].items():
            state_table.add_row(state, str(count))
        
        console.print(state_table)
        console.print()


def save_results(results: dict, output_dir: str, run_id: str):
    """Save results to disk."""
    run_dir = Path(output_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Saving results to {run_dir}")
    
    # Save trade list
    trades_data = []
    for trade in results['trades']:
        trades_data.append({
            'trade_id': trade.trade_id,
            'playbook': trade.playbook_name,
            'direction': trade.direction,
            'entry_timestamp': trade.entry_timestamp.isoformat(),
            'exit_timestamp': trade.exit_timestamp.isoformat() if trade.exit_timestamp else None,
            'entry_price': trade.entry_price,
            'exit_price': trade.exit_price,
            'exit_reason': trade.exit_reason,
            'realized_r': trade.realized_r,
            'mfe_r': trade.mfe_r,
            'mae_r': trade.mae_r,
            'auction_state': trade.auction_state,
            'salvage_triggered': trade.salvage_triggered,
        })
    
    trades_df = pd.DataFrame(trades_data)
    trades_df.to_csv(run_dir / "trades.csv", index=False)
    trades_df.to_parquet(run_dir / "trades.parquet")
    
    # Save metrics
    metrics = {
        'total_trades': results['total_trades'],
        'winning_trades': results['winning_trades'],
        'losing_trades': results['losing_trades'],
        'win_rate': results['win_rate'],
        'expectancy': results['expectancy'],
        'cumulative_r': results['cumulative_r'],
        'avg_winner': results['avg_winner'],
        'avg_loser': results['avg_loser'],
        'max_win': results['max_win'],
        'max_loss': results['max_loss'],
        'avg_mfe': results['avg_mfe'],
        'avg_mae': results['avg_mae'],
        'salvage_count': results['salvage_count'],
        'trades_by_playbook': results['trades_by_playbook'],
        'trades_by_state': results['trades_by_state'],
    }
    
    with open(run_dir / "metrics.json", 'w') as f:
        json.dump(metrics, f, indent=2, default=str)
    
    logger.info(f"Results saved to {run_dir}")
    
    return run_dir


def main():
    """Main execution."""
    args = parse_args()
    
    # Setup
    setup_logging(args.verbose)
    
    console.print()
    console.rule("[bold green]ORB 2.0 Integrated Backtest[/bold green]")
    console.print()
    
    # Create config
    config = ORB2Config(
        enable_pb1=not args.disable_pb1,
        enable_pb2=not args.disable_pb2,
        enable_pb3=not args.disable_pb3,
        use_salvage=not args.disable_salvage,
        use_context_exclusion=False,  # Disabled for first run
        use_probability_gating=False,  # Disabled (no model yet)
    )
    
    logger.info(f"ORB 2.0 Config: PB1={config.enable_pb1}, PB2={config.enable_pb2}, PB3={config.enable_pb3}, Salvage={config.use_salvage}")
    
    # Create engine
    engine = ORB2Engine(config)
    
    # Fetch data
    console.print("[cyan]Fetching data...[/cyan]")
    bars = fetch_data(
        symbol=args.symbol,
        start_date=args.start,
        end_date=args.end,
        use_synthetic=args.synthetic,
        use_databento=args.databento,
        databento_dir=args.databento_dir,
    )
    
    if bars is None:
        console.print("[red]Failed to fetch data, exiting[/red]")
        return 1
    
    console.print(f"[green]Fetched {len(bars):,} bars[/green]")
    console.print()
    
    # Run backtest
    console.print("[cyan]Running ORB 2.0 backtest...[/cyan]")
    
    try:
        results = engine.run(
            bars=bars,
            instrument=args.symbol,
        )
        
        # Print results
        print_results_table(results)
        
        # Save results
        run_id = f"orb2_{args.symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        run_dir = save_results(results, args.output_dir, run_id)
        
        # Final message
        console.rule("[bold green]Backtest Complete[/bold green]")
        console.print()
        console.print(f"[green]✓ Results saved to: {run_dir}[/green]")
        console.print(f"[cyan]✓ Run ID: {run_id}[/cyan]")
        console.print()
        
        return 0
    
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

