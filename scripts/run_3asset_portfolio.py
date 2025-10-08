"""
Run 3-asset portfolio backtest: ES, NQ, 6E

Using optimized ES parameters from Round 1 optimization.
Goal: Test if diversification improves overall P/L.
"""

from pathlib import Path
from datetime import date, datetime
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from orb_confluence.backtest.multi_instrument_orchestrator import (
    MultiInstrumentOrchestrator,
    OrchestratorConfig
)
from orb_confluence.strategy.prop_governance import TOPSTEP_50K
from loguru import logger


def main():
    # Generate timestamped run ID
    run_id = f"3asset_{datetime.now().strftime('%m-%d_%H-%M')}"
    
    logger.info("="*80)
    logger.info("3-ASSET PORTFOLIO BACKTEST")
    logger.info("="*80)
    logger.info("Instruments: ES, NQ, 6E")
    logger.info("ES Config: Optimized Round 1 (T1=1.0R, 60%, BE=0.4R)")
    logger.info("Dataset: 2025 YTD (Jan 1 - Oct 7)")
    logger.info(f"Run ID: {run_id}")
    logger.info("="*80)
    logger.info("")
    
    # Configure backtest
    config = OrchestratorConfig(
        prop_rules=TOPSTEP_50K,
        instruments=['ES', 'NQ', '6E'],  # 3 instruments
        start_date=date(2025, 1, 1),
        end_date=date(2025, 10, 7),
        data_directory=Path('data_cache/databento_1m'),
        output_directory=Path(f'runs/{run_id}'),
        max_concurrent_trades=2,
        correlation_aware_sizing=True  # Account for ES/NQ correlation
    )
    
    # Run backtest
    orchestrator = MultiInstrumentOrchestrator(config=config)
    results = orchestrator.run_backtest()
    
    # Summary
    trades = results['trades']
    
    logger.info("")
    logger.info("="*80)
    logger.info("3-ASSET PORTFOLIO RESULTS")
    logger.info("="*80)
    
    if len(trades) > 0:
        # Overall metrics
        total_r = sum(t.outcome.realized_r for t in trades)
        total_pnl = sum(t.outcome.realized_dollars for t in trades)
        winners = [t for t in trades if t.outcome.realized_dollars > 0]
        losers = [t for t in trades if t.outcome.realized_dollars <= 0]
        
        logger.info(f"Total Trades: {len(trades)}")
        logger.info(f"Winners: {len(winners)} ({len(winners)/len(trades)*100:.1f}%)")
        logger.info(f"Expectancy: {total_r/len(trades):.3f}R per trade")
        logger.info(f"Total R: {total_r:.2f}R")
        logger.info(f"Total P/L: ${total_pnl:.0f}")
        
        if winners and losers:
            avg_winner = sum(t.outcome.realized_r for t in winners) / len(winners)
            avg_loser = sum(t.outcome.realized_r for t in losers) / len(losers)
            logger.info(f"Avg Winner: {avg_winner:.2f}R")
            logger.info(f"Avg Loser: {avg_loser:.2f}R")
            logger.info(f"R:R Ratio: {abs(avg_winner/avg_loser):.3f}:1")
        
        logger.info("")
        
        # Per-instrument breakdown
        logger.info("Per-Instrument Breakdown:")
        logger.info("-" * 80)
        for instrument in ['ES', 'NQ', '6E']:
            inst_trades = [t for t in trades if t.instrument == instrument]
            if inst_trades:
                inst_pnl = sum(t.outcome.realized_dollars for t in inst_trades)
                inst_winners = [t for t in inst_trades if t.outcome.realized_dollars > 0]
                inst_wr = len(inst_winners) / len(inst_trades) * 100
                inst_r = sum(t.outcome.realized_r for t in inst_trades)
                logger.info(
                    f"  {instrument}: {len(inst_trades)} trades, "
                    f"${inst_pnl:+.0f} P/L, "
                    f"{inst_wr:.1f}% WR, "
                    f"{inst_r/len(inst_trades):+.3f}R exp"
                )
        
        logger.info("")
        
        # Compare to ES-only
        logger.info("📊 PORTFOLIO vs ES-ONLY:")
        logger.info("-" * 80)
        logger.info(f"  ES Only (optimized):  -$291 P/L, -0.219R exp, 58.2% WR")
        logger.info(f"  3-Asset Portfolio:    ${total_pnl:+.0f} P/L, {total_r/len(trades):+.3f}R exp, {len(winners)/len(trades)*100:.1f}% WR")
        
        improvement = total_pnl - (-291)
        if improvement > 0:
            logger.success(f"  🎉 Portfolio is ${improvement:+.0f} BETTER!")
        elif improvement > -100:
            logger.info(f"  Similar performance (${improvement:+.0f})")
        else:
            logger.warning(f"  Portfolio is ${improvement:.0f} worse")
        
    else:
        logger.warning("No trades generated!")
    
    logger.info("")
    logger.info(f"Results saved to: runs/{run_id}/")
    logger.info("="*80)
    logger.success("✅ Backtest complete! Load in Streamlit dashboard.")


if __name__ == "__main__":
    main()
