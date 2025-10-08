#!/usr/bin/env python3
"""Run multi-instrument ORB backtest using the orchestrator."""

import sys
sys.path.insert(0, '.')

from pathlib import Path
from datetime import date, datetime
from loguru import logger

from orb_confluence.backtest.multi_instrument_orchestrator import (
    MultiInstrumentOrchestrator,
    OrchestratorConfig
)
from orb_confluence.strategy.prop_governance import TOPSTEP_50K


def main():
    """Run multi-instrument backtest."""
    
    # Configure logging
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level="INFO"
    )
    
    # Generate timestamped run ID
    now = datetime.now()
    run_id = f"multi_instrument_{now.strftime('%m-%d_%H-%M')}"
    
    # Configure backtest for 2025 YTD with professional Databento data
    config = OrchestratorConfig(
        prop_rules=TOPSTEP_50K,
        instruments=['ES', 'NQ', 'GC', '6E'],  # All 4 instruments with pro data
        start_date=date(2025, 1, 1),    # 2025 YTD
        end_date=date(2025, 10, 7),     # Today
        data_directory=Path('data_cache/databento_1m'),  # Professional Databento data
        output_directory=Path(f'runs/{run_id}'),
        max_concurrent_trades=2,
        correlation_aware_sizing=True
    )
    
    logger.info("="*80)
    logger.info("MULTI-INSTRUMENT ORB BACKTEST")
    logger.info("="*80)
    logger.info(f"Instruments: {', '.join(config.instruments)}")
    logger.info(f"Period: {config.start_date} to {config.end_date}")
    logger.info(f"Account: ${config.prop_rules.account_size:,.0f}")
    logger.info(f"Target: ${config.prop_rules.profit_target:,.0f}")
    logger.info(f"Daily Limit: ${config.prop_rules.daily_loss_limit:,.0f}")
    logger.info("="*80)
    
    # Create orchestrator
    orchestrator = MultiInstrumentOrchestrator(config)
    
    # Run backtest
    try:
        results = orchestrator.run_backtest()
        
        # Display results
        logger.info("\n" + "="*80)
        logger.info("BACKTEST RESULTS")
        logger.info("="*80)
        logger.info(f"Total Trades: {results['total_trades']}")
        logger.info(f"Winners: {results['winning_trades']} ({results['win_rate']*100:.1f}%)")
        logger.info(f"Losers: {results['losing_trades']}")
        logger.info(f"Expectancy: {results['expectancy']:+.3f}R")
        logger.info(f"Total R: {results['total_r']:+.2f}R")
        logger.info(f"Total P/L: ${results['total_dollars']:+,.0f}")
        logger.info(f"Final Balance: ${results['final_balance']:,.0f}")
        logger.info(f"Peak Balance: ${results['peak_balance']:,.0f}")
        logger.info(f"Max Drawdown: ${results['max_drawdown']:,.0f}")
        logger.info(f"Profit Target: {results['profit_target_pct']:.1f}%")
        logger.info("\nTrades by Instrument:")
        for instrument, count in results['trades_by_instrument'].items():
            logger.info(f"  {instrument}: {count} trades")
        logger.info(f"\nAvg Bars Held: {results['avg_bars_held']:.1f}")
        logger.info(f"% Reached +1R: {results['pct_reached_1r']:.1f}%")
        logger.info("="*80)
        
        return 0
        
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
