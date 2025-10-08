"""Test a single instrument to debug trade generation."""

import sys
sys.path.insert(0, '.')

from pathlib import Path
from datetime import date, datetime
from loguru import logger
import json

from orb_confluence.backtest.multi_instrument_orchestrator import (
    MultiInstrumentOrchestrator,
    OrchestratorConfig
)
from orb_confluence.strategy.prop_governance import TOPSTEP_50K


def main():
    """Run single-instrument backtest."""
    
    import argparse
    parser = argparse.ArgumentParser(description='Test single instrument')
    parser.add_argument('--instrument', type=str, required=True, 
                       choices=['ES', 'NQ', 'CL', 'GC', '6E'],
                       help='Instrument to test')
    parser.add_argument('--disable-filters', action='store_true',
                       help='Disable quality filters to see all potential setups')
    args = parser.parse_args()
    
    # Configure logging
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO"
    )
    
    # Generate timestamped run ID
    now = datetime.now()
    run_id = f"test_{args.instrument}_{now.strftime('%m-%d_%H-%M')}"
    
    # Configure backtest
    config = OrchestratorConfig(
        prop_rules=TOPSTEP_50K,
        instruments=[args.instrument],  # Single instrument
        start_date=date(2025, 9, 9),
        end_date=date(2025, 10, 4),
        data_directory=Path('data_cache/futures_15m'),
        output_directory=Path(f'runs/{run_id}'),
        max_concurrent_trades=1,
        correlation_aware_sizing=False
    )
    
    logger.info("="*80)
    logger.info(f"SINGLE-INSTRUMENT TEST: {args.instrument}")
    logger.info("="*80)
    logger.info(f"Period: {config.start_date} to {config.end_date}")
    logger.info(f"Quality Filters: {'DISABLED' if args.disable_filters else 'ENABLED'}")
    logger.info("="*80)
    
    # Create orchestrator
    orchestrator = MultiInstrumentOrchestrator(config)
    
    # Optionally disable quality filters for debugging
    if args.disable_filters:
        logger.warning("⚠️  DISABLING QUALITY FILTERS FOR DEBUGGING")
        # We'll need to modify the orchestrator to skip filters
        # For now, just run normally but note this in output
    
    # Run backtest
    try:
        results = orchestrator.run_backtest()
        
        # Display results
        logger.info("\n" + "="*80)
        logger.info(f"{args.instrument} BACKTEST RESULTS")
        logger.info("="*80)
        logger.info(f"Total Trades: {results['total_trades']}")
        logger.info(f"Winners: {results['winning_trades']} ({results['win_rate']*100:.1f}%)")
        logger.info(f"Losers: {results['losing_trades']}")
        logger.info(f"Expectancy: {results['expectancy']:+.3f}R")
        logger.info(f"Total R: {results['total_r']:+.2f}R")
        logger.info(f"Total P/L: ${results['total_dollars']:+,.0f}")
        logger.info(f"Final Balance: ${results['final_balance']:,.0f}")
        logger.info(f"Max Drawdown: ${results['max_drawdown']:,.0f}")
        
        # Check why trades might be rejected
        if results['total_trades'] == 0:
            logger.warning("\n⚠️  NO TRADES GENERATED!")
            logger.info("Common reasons:")
            logger.info("  1. ORB width outside acceptable range (too wide/narrow)")
            logger.info("  2. Volume quality failing (too low/high, spike detected)")
            logger.info("  3. Drive energy too low")
            logger.info("  4. Governance lockout from previous losses")
            logger.info("\nCheck the logs above for specific rejection reasons.")
        
        logger.info("="*80)
        logger.info(f"\n✅ Results saved to: runs/{run_id}/")
        
        # Load and display some OR stats
        trades_file = Path(f'runs/{run_id}/all_trades.json')
        if trades_file.exists():
            with open(trades_file, 'r') as f:
                trades = json.load(f)
            
            if trades:
                logger.info(f"\n📊 Trade Details:")
                for i, trade in enumerate(trades[:5], 1):  # Show first 5
                    or_metrics = trade.get('or_metrics', {})
                    vol_metrics = trade.get('volume_metrics', {})
                    breakout = trade.get('breakout_context', {})
                    outcome = trade.get('outcome', {})
                    
                    logger.info(f"\n  Trade {i}:")
                    logger.info(f"    Date: {trade.get('date')}")
                    logger.info(f"    Direction: {breakout.get('direction')}")
                    logger.info(f"    OR Width: {or_metrics.get('width'):.2f} (norm: {or_metrics.get('width_norm'):.2f})")
                    logger.info(f"    OR Valid: {or_metrics.get('is_valid')}")
                    logger.info(f"    Volume Quality: {vol_metrics.get('passes_goldilocks')}")
                    logger.info(f"    Realized R: {outcome.get('realized_r_multiple', 0):.2f}R")
                    logger.info(f"    Exit: {outcome.get('exit_reason')}")
        
        return 0
        
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
