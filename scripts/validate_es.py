"""Validation backtest for ES with optimized parameters."""

from pathlib import Path
from datetime import date
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from orb_confluence.backtest.multi_instrument_orchestrator import (
    MultiInstrumentOrchestrator,
    OrchestratorConfig
)
from orb_confluence.strategy.prop_governance import TOPSTEP_50K
from loguru import logger

def main():
    logger.info("="*80)
    logger.info("ES VALIDATION BACKTEST - Optimized Parameters")
    logger.info("="*80)
    logger.info("Config: T1=1.0R (60%), T2=3.0R, BE=0.4R, Stop=1.4R")
    logger.info("="*80)
    
    config = OrchestratorConfig(
        prop_rules=TOPSTEP_50K,
        instruments=['ES'],  # ES only
        start_date=date(2025, 1, 1),
        end_date=date(2025, 10, 7),
        data_directory=Path('data_cache/databento_1m'),
        output_directory=Path('runs/es_optimized_validation'),
        max_concurrent_trades=2,
        correlation_aware_sizing=False
    )
    
    orchestrator = MultiInstrumentOrchestrator(config=config)
    results = orchestrator.run_backtest()
    
    # Analyze results
    trades = results['trades']
    
    logger.info("")
    logger.info("="*80)
    logger.info("VALIDATION RESULTS")
    logger.info("="*80)
    logger.info(f"Total Trades: {len(trades)}")
    
    if len(trades) > 0:
        total_r = sum(t.outcome.realized_r for t in trades)
        total_pnl = sum(t.outcome.realized_dollars for t in trades)
        winners = [t for t in trades if t.outcome.realized_dollars > 0]
        losers = [t for t in trades if t.outcome.realized_dollars <= 0]
        
        logger.info(f"Winners: {len(winners)} ({len(winners)/len(trades)*100:.1f}%)")
        logger.info(f"Expectancy: {total_r/len(trades):.3f}R per trade")
        logger.info(f"Total R: {total_r:.2f}R")
        logger.info(f"Total P/L: ${total_pnl:.0f}")
        logger.info(f"Avg Winner: {sum(t.outcome.realized_r for t in winners)/len(winners):.2f}R" if winners else "N/A")
        logger.info(f"Avg Loser: {sum(t.outcome.realized_r for t in losers)/len(losers):.2f}R" if losers else "N/A")
        logger.success(f"✅ Validation complete!")
    else:
        logger.warning("No trades generated")
    
    logger.info("="*80)

if __name__ == "__main__":
    main()
