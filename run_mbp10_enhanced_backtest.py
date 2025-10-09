"""
Multi-Playbook Strategy Backtest with MBP-10 Order Flow Integration

This is the FULL SYSTEM test with Week 2 + Week 3 enhancements:
- Entry filters (OFI + depth imbalance)
- Exit timing (OFI reversals + institutional resistance)

Expected Results:
- Expectancy: 0.12-0.18R (vs 0.05R baseline)
- Win Rate: 52-55% (vs 48% baseline)
- Sept 14-15: 5-6 trades (vs 10 baseline)

Author: Nick Burner
Date: October 9, 2025
"""

import sys
from pathlib import Path
import pandas as pd
from loguru import logger
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from orb_confluence.data.databento_loader import DatabentoLoader
from orb_confluence.data.mbp10_loader import MBP10Loader
from orb_confluence.strategy.playbooks.vwap_magnet import VWAPMagnetPlaybook
from orb_confluence.strategy.playbooks.ib_fade import IBFadePlaybook
from orb_confluence.strategy.playbooks.momentum_continuation import MomentumContinuationPlaybook
from orb_confluence.strategy.playbooks.opening_drive_reversal import OpeningDriveReversalPlaybook
from orb_confluence.strategy.multi_playbook_strategy import MultiPlaybookStrategy
from orb_confluence.backtest.multi_playbook_backtest import MultiPlaybookBacktest, BacktestConfig


# Configure logging
logger.remove()
logger.add(sys.stdout, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>")
logger.add("mbp10_backtest.log", level="DEBUG")


def main():
    """Run backtest with full MBP-10 integration."""
    
    logger.info("=" * 80)
    logger.info("🚀 MULTI-PLAYBOOK BACKTEST WITH MBP-10 ORDER FLOW")
    logger.info("=" * 80)
    
    # Configuration
    SYMBOL = "ES"
    START_DATE = "2025-09-14"  # Start with Sept 14-15 (the big profit days)
    END_DATE = "2025-09-16"
    INITIAL_CAPITAL = 100000
    BASE_RISK = 0.01
    
    logger.info(f"\n📅 Backtest Period: {START_DATE} to {END_DATE}")
    logger.info(f"💰 Initial Capital: ${INITIAL_CAPITAL:,}")
    logger.info(f"⚠️  Base Risk: {BASE_RISK:.1%}\n")
    
    # Step 1: Load 1-minute OHLCV data
    logger.info("📊 Loading 1-minute price data...")
    loader_1m = DatabentoLoader(data_directory="data_cache/databento_1m")
    bars_1m = loader_1m.load(symbol=SYMBOL, start_date=START_DATE, end_date=END_DATE)
    
    if bars_1m is None or len(bars_1m) == 0:
        logger.error("❌ No 1m data loaded. Exiting.")
        return
    
    logger.info(f"  ✅ Loaded {len(bars_1m):,} 1-minute bars")
    logger.info(f"  📅 Date range: {bars_1m.index[0]} to {bars_1m.index[-1]}")
    
    # Step 2: Create daily bars
    logger.info("\n📊 Creating daily bars...")
    if not isinstance(bars_1m.index, pd.DatetimeIndex):
        bars_1m.index = pd.to_datetime(bars_1m.index)
    
    bars_daily = bars_1m.resample('D').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
    }).dropna()
    
    logger.info(f"  ✅ Created {len(bars_daily)} daily bars")
    
    # Step 3: Load MBP-10 order book data
    logger.info("\n📖 Loading MBP-10 order book data...")
    try:
        mbp10_loader = MBP10Loader(data_directory="data_cache/GLBX-20251008-HHT7VXJSSJ")
        logger.info("  ✅ MBP10Loader initialized")
        logger.info("  ℹ️  Order flow filters: ACTIVE")
        logger.info("  ℹ️  Exit timing enhancements: ACTIVE")
    except Exception as e:
        logger.warning(f"  ⚠️  MBP-10 data not available: {e}")
        logger.warning("  ℹ️  Running without order flow enhancements")
        mbp10_loader = None
    
    # Step 4: Initialize playbooks
    logger.info("\n🎯 Initializing playbooks...")
    playbooks = [
        VWAPMagnetPlaybook(
            band_multiplier=2.0,
            min_rejection_velocity=0.3,
        ),
        IBFadePlaybook(
            ib_minutes=60,
            extension_threshold=1.5,
            max_aer=0.65,
        ),
        MomentumContinuationPlaybook(
            min_iqf=1.8,
            pullback_min=0.382,
            pullback_max=0.618,
        ),
        OpeningDriveReversalPlaybook(
            min_drive_minutes=5,
            max_drive_minutes=15,
            min_tape_decline=0.3,
        ),
    ]
    
    for pb in playbooks:
        logger.info(f"  ✅ {pb.name} ({pb.playbook_type})")
    
    # Step 5: Initialize strategy
    logger.info("\n🎮 Initializing Multi-Playbook Strategy...")
    strategy = MultiPlaybookStrategy(
        playbooks=playbooks,
        account_size=INITIAL_CAPITAL,
        base_risk=BASE_RISK,
        max_simultaneous_positions=3,
        enable_signal_arbitration=True,
        enable_correlation_weighting=True,
        mbp10_loader=mbp10_loader,  # Week 3: Order flow integration
    )
    
    logger.info("  ✅ Strategy initialized")
    
    # Step 6: Fit regime classifier
    logger.info("\n🧠 Fitting regime classifier...")
    try:
        strategy.fit_regime_classifier(bars_1m.head(1000))
        logger.info("  ✅ Regime classifier fitted")
    except Exception as e:
        logger.warning(f"  ⚠️  Regime classifier failed: {e}")
        logger.warning("  ℹ️  Continuing without regime classification")
    
    # Step 7: Run backtest
    logger.info("\n⚙️  Running backtest...")
    logger.info("  ℹ️  This may take a few minutes with MBP-10 data...")
    
    config = BacktestConfig(
        symbol=SYMBOL,
        start_date=START_DATE,
        end_date=END_DATE,
        initial_capital=INITIAL_CAPITAL,
        point_value=50.0,
    )
    
    backtest = MultiPlaybookBacktest(
        strategy=strategy,
        bars_1m=bars_1m,
        bars_daily=bars_daily,
        config=config,
        start_date=None,  # Already filtered
        end_date=None,
    )
    
    # Run the backtest
    try:
        results = backtest.run()
        logger.info("  ✅ Backtest complete!")
    except Exception as e:
        logger.error(f"  ❌ Backtest failed: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Step 8: Display results
    logger.info("\n" + "=" * 80)
    logger.info("📊 BACKTEST RESULTS")
    logger.info("=" * 80)
    
    # Extract metrics
    trades = results.get('trades', [])
    equity_history = results.get('equity_history', [])
    
    if len(trades) == 0:
        logger.warning("⚠️  NO TRADES GENERATED")
        logger.warning("This could mean:")
        logger.warning("  1. Regime classifier filtered all opportunities")
        logger.warning("  2. MBP-10 filters were too strict")
        logger.warning("  3. No valid setups in this period")
        return
    
    # Calculate metrics
    winning_trades = [t for t in trades if t['r_multiple'] > 0]
    losing_trades = [t for t in trades if t['r_multiple'] <= 0]
    
    total_r = sum(t['r_multiple'] for t in trades)
    avg_r = total_r / len(trades) if trades else 0
    win_rate = len(winning_trades) / len(trades) if trades else 0
    
    # Playbook breakdown
    playbook_trades = {}
    for t in trades:
        pb_name = t.get('playbook_name', 'Unknown')
        if pb_name not in playbook_trades:
            playbook_trades[pb_name] = []
        playbook_trades[pb_name].append(t)
    
    # Exit reason breakdown
    exit_reasons = {}
    for t in trades:
        reason = t.get('exit_reason', 'Unknown')
        exit_reasons[reason] = exit_reasons.get(reason, 0) + 1
    
    # Display
    logger.info(f"\n📈 PERFORMANCE:")
    logger.info(f"  Total Trades:       {len(trades)}")
    logger.info(f"  Winning Trades:     {len(winning_trades)} ({win_rate:.1%})")
    logger.info(f"  Losing Trades:      {len(losing_trades)}")
    logger.info(f"  Expectancy:         {avg_r:.3f}R")
    logger.info(f"  Cumulative R:       {total_r:.2f}R")
    
    if equity_history:
        final_equity = equity_history[-1]
        total_pnl = final_equity - INITIAL_CAPITAL
        roi = (total_pnl / INITIAL_CAPITAL) * 100
        logger.info(f"  Final Equity:       ${final_equity:,.2f}")
        logger.info(f"  Total P&L:          ${total_pnl:,.2f} ({roi:+.2f}%)")
    
    logger.info(f"\n🎯 PLAYBOOK BREAKDOWN:")
    for pb_name, pb_trades in sorted(playbook_trades.items(), key=lambda x: len(x[1]), reverse=True):
        pb_r = sum(t['r_multiple'] for t in pb_trades)
        pb_wins = len([t for t in pb_trades if t['r_multiple'] > 0])
        pb_wr = pb_wins / len(pb_trades) if pb_trades else 0
        logger.info(f"  {pb_name:25s} {len(pb_trades):3d} trades | {pb_wr:.1%} WR | {pb_r:+.2f}R")
    
    logger.info(f"\n🚪 EXIT REASONS:")
    for reason, count in sorted(exit_reasons.items(), key=lambda x: x[1], reverse=True):
        pct = count / len(trades) * 100
        logger.info(f"  {reason:25s} {count:3d} trades ({pct:.1f}%)")
    
    # Check for order flow exits
    order_flow_exits = exit_reasons.get('OFI_REVERSAL', 0) + exit_reasons.get('INSTITUTIONAL_RESISTANCE', 0)
    if order_flow_exits > 0:
        logger.info(f"\n✅ ORDER FLOW EXITS: {order_flow_exits} trades")
        logger.info("  Week 3 enhancements are WORKING!")
    else:
        logger.info(f"\n⚠️  NO ORDER FLOW EXITS DETECTED")
        logger.info("  This could mean:")
        logger.info("    1. No OFI reversals occurred")
        logger.info("    2. No large orders detected")
        logger.info("    3. Stops/salvage hit first")
    
    # Save results
    logger.info("\n💾 Saving results...")
    
    run_id = f"mbp10_enhanced_{SYMBOL}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_dir = f"runs/{run_id}"
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # Save trades
    trades_df = pd.DataFrame(trades)
    trades_df.to_json(f"{output_dir}/all_trades.json", orient="records", date_format="iso")
    logger.info(f"  ✅ Saved trades to {output_dir}/all_trades.json")
    
    # Save summary
    summary = {
        'run_id': run_id,
        'symbol': SYMBOL,
        'start_date': START_DATE,
        'end_date': END_DATE,
        'initial_capital': INITIAL_CAPITAL,
        'final_equity': equity_history[-1] if equity_history else INITIAL_CAPITAL,
        'total_pnl': equity_history[-1] - INITIAL_CAPITAL if equity_history else 0,
        'total_trades': len(trades),
        'winning_trades': len(winning_trades),
        'losing_trades': len(losing_trades),
        'win_rate': win_rate,
        'expectancy': avg_r,
        'cumulative_r': total_r,
        'mbp10_enabled': mbp10_loader is not None,
        'order_flow_exits': order_flow_exits,
        'playbooks': [pb.name for pb in playbooks],
    }
    
    import json
    with open(f"{output_dir}/summary.json", 'w') as f:
        json.dump(summary, f, indent=2)
    logger.info(f"  ✅ Saved summary to {output_dir}/summary.json")
    
    # Save equity curve
    equity_df = pd.DataFrame({
        'timestamp': results.get('date_history', []),
        'equity': equity_history,
    })
    equity_df.to_csv(f"{output_dir}/equity_curve.csv", index=False)
    logger.info(f"  ✅ Saved equity curve to {output_dir}/equity_curve.csv")
    
    logger.info(f"\n✅ BACKTEST COMPLETE! Run ID: {run_id}")
    logger.info("View results on Streamlit dashboard")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()

