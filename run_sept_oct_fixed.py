"""Run Sept-Oct 2025 backtest with fixed playbook integration."""

import sys
from pathlib import Path
import pandas as pd
from loguru import logger
from datetime import datetime
import json
import time
from dataclasses import asdict

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from orb_confluence.data.databento_loader import DatabentoLoader
from orb_confluence.data.mbp10_loader import MBP10Loader
from orb_confluence.strategy.playbooks.ib_fade import IBFadePlaybook
from orb_confluence.strategy.playbooks.momentum_continuation import MomentumContinuationPlaybook
from orb_confluence.strategy.playbooks.opening_drive_reversal import OpeningDriveReversalPlaybook
from orb_confluence.strategy.multi_playbook_strategy import MultiPlaybookStrategy
from orb_confluence.backtest.multi_playbook_backtest import MultiPlaybookBacktest, BacktestConfig

# Configure logging
logger.remove()
logger.add("sept_oct_fixed.log", level="INFO")
logger.add(sys.stdout, level="INFO")


def run_sept_oct():
    print("=" * 80)
    print("🚀 SEPTEMBER-OCTOBER 2025 BACKTEST (FIXED PLAYBOOKS)")
    print("=" * 80)
    print()
    
    START_DATE = "2025-09-07"
    END_DATE = "2025-10-09"
    SYMBOL = "ES"
    INITIAL_CAPITAL = 100000
    BASE_RISK = 0.01
    
    logger.info(f"📅 Period: {START_DATE} - {END_DATE}")
    logger.info(f"💰 Historical Performance: +$33,568 (625 trades)")
    print()
    
    # Load data
    logger.info("📦 Loading 1-minute OHLCV data...")
    loader_1m = DatabentoLoader(data_directory="data_cache/databento_1m")
    bars_1m = loader_1m.load(symbol=SYMBOL, start_date=START_DATE, end_date=END_DATE)
    
    if bars_1m is None or len(bars_1m) == 0:
        logger.error(f"❌ No data for {START_DATE} to {END_DATE}")
        return None
    logger.info(f"✅ Loaded {len(bars_1m):,} 1-minute bars")
    
    # Create daily bars
    if not isinstance(bars_1m.index, pd.DatetimeIndex):
        bars_1m.index = pd.to_datetime(bars_1m.index)
    
    bars_daily = bars_1m.resample('D').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
    }).dropna()
    logger.info(f"✅ Created {len(bars_daily)} daily bars")
    
    # Load MBP-10
    logger.info("📦 Loading MBP-10 data...")
    try:
        mbp10_paths = [
            "data_cache/MBP-10/2025-09",
            "data_cache/MBP-10/2025-10",
        ]
        
        mbp10_loader = None
        for path in mbp10_paths:
            if Path(path).exists():
                mbp10_loader = MBP10Loader(data_directory=path)
                logger.info(f"✅ MBP-10 from {path}")
                break
    except Exception as e:
        logger.warning(f"⚠️  MBP-10 unavailable: {e}")
        mbp10_loader = None
    
    print()
    logger.info("📦 Initializing strategy with FIXED playbooks...")
    
    # Initialize with FIXED parameters
    playbooks = [
        OpeningDriveReversalPlaybook(min_drive_range=3.0, min_tape_decline=0.2),
        IBFadePlaybook(ib_minutes=30, extension_threshold=1.3, max_aer=0.70),
        MomentumContinuationPlaybook(min_iqf=1.0, pullback_min=0.25, pullback_max=0.75),
    ]
    
    logger.info(f"✅ Initialized {len(playbooks)} playbooks:")
    for pb in playbooks:
        logger.info(f"  - {pb.name}: {pb.preferred_regimes}")
    
    strategy = MultiPlaybookStrategy(
        playbooks=playbooks,
        account_size=INITIAL_CAPITAL,
        base_risk=BASE_RISK,
        max_simultaneous_positions=3,
        enable_signal_arbitration=True,
        enable_correlation_weighting=True,
        mbp10_loader=mbp10_loader,
    )
    
    # Fit regime classifier
    logger.info("📦 Fitting regime classifier...")
    try:
        fit_bars = bars_1m.head(1000) if len(bars_1m) >= 1000 else bars_1m
        strategy.fit_regime_classifier(fit_bars)
        logger.info("✅ Regime classifier fitted")
    except Exception as e:
        logger.warning(f"⚠️  Regime classifier failed: {e}")
    
    print()
    print("=" * 80)
    print("⚙️  RUNNING BACKTEST...")
    print("=" * 80)
    print()
    
    config = BacktestConfig(
        initial_capital=INITIAL_CAPITAL,
        point_value=50.0,
    )
    
    backtest = MultiPlaybookBacktest(
        strategy=strategy,
        bars_1m=bars_1m,
        bars_daily=bars_daily,
        config=config,
        start_date=None,
        end_date=None,
    )
    
    start_time = time.time()
    results = backtest.run()
    elapsed_time = time.time() - start_time
    
    print()
    print("=" * 80)
    print("📊 SEPTEMBER-OCTOBER 2025 RESULTS")
    print("=" * 80)
    print()
    
    trades = results.trades if hasattr(results, 'trades') else []
    metrics = results.metrics if hasattr(results, 'metrics') else {}
    
    print(f"📈 PERFORMANCE:")
    print(f"  Total Trades:      {len(trades)}")
    if metrics and len(trades) > 0:
        print(f"  Win Rate:          {metrics.get('win_rate', 0)*100:.1f}%")
        print(f"  Expectancy:        {metrics.get('expectancy_r', 0):.3f}R")
        print(f"  Total R:           {metrics.get('average_r', 0) * len(trades):.2f}R")
        print(f"  Profit Factor:     {metrics.get('profit_factor', 0):.2f}")
        print(f"  Total Return:      {metrics.get('total_return', 0)*100:.1f}%")
        print(f"  Net PNL:           ${metrics.get('total_return', 0) * INITIAL_CAPITAL:,.2f}")
    print()
    
    # Playbook breakdown
    if trades:
        playbook_stats = {}
        for t in trades:
            pb_name = t.playbook_name if hasattr(t, 'playbook_name') else 'Unknown'
            if pb_name not in playbook_stats:
                playbook_stats[pb_name] = {'wins': 0, 'losses': 0, 'total_r': 0, 'count': 0}
            
            r_mult = t.r_multiple if hasattr(t, 'r_multiple') else 0
            playbook_stats[pb_name]['count'] += 1
            playbook_stats[pb_name]['total_r'] += r_mult
            if r_mult > 0:
                playbook_stats[pb_name]['wins'] += 1
            else:
                playbook_stats[pb_name]['losses'] += 1
        
        print("🎯 PLAYBOOK BREAKDOWN:")
        for pb_name, stats in playbook_stats.items():
            win_rate = (stats['wins'] / stats['count']) * 100 if stats['count'] > 0 else 0
            print(f"  {pb_name:<30} {stats['count']} trades | {win_rate:.1f}% WR | {stats['total_r']:+.2f}R")
        print()
    
    print()
    print("=" * 80)
    print("💰 COMPARISON TO HISTORICAL")
    print("=" * 80)
    print(f"  Historical: 625 trades, +$33,568")
    print(f"  Fixed:      {len(trades)} trades, ${metrics.get('total_return', 0) * INITIAL_CAPITAL:+,.2f}")
    print(f"  Delta:      {len(trades) - 625:+d} trades, ${(metrics.get('total_return', 0) * INITIAL_CAPITAL) - 33568:+,.2f}")
    print("=" * 80)
    
    print(f"\nProcessing Time: {elapsed_time/60:.1f} minutes")
    
    # Save results
    run_id = f"sept_oct_fixed_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_dir = Path(f"runs/{run_id}")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    summary_dict = {
        'run_id': run_id,
        'total_trades': len(trades),
        'win_rate': metrics.get('win_rate', 0) if metrics else 0,
        'expectancy': metrics.get('expectancy_r', 0) if metrics else 0,
        'cumulative_r': metrics.get('average_r', 0) * len(trades) if metrics else 0,
        'profit_factor': metrics.get('profit_factor', 0) if metrics else 0,
        'total_pnl': metrics.get('total_return', 0) * INITIAL_CAPITAL if metrics else 0,
    }
    
    with open(output_dir / "summary.json", 'w') as f:
        json.dump(summary_dict, f, indent=2)
    
    if trades:
        trades_dicts = [asdict(t) for t in trades]
        trades_df = pd.DataFrame(trades_dicts)
        trades_df.to_json(output_dir / "all_trades.json", orient="records", date_format="iso")
    
    logger.info(f"✅ Results saved to: {output_dir}/")
    logger.info(f"🆔 Run ID: {run_id}")
    
    return run_id


if __name__ == "__main__":
    try:
        run_id = run_sept_oct()
        print()
        print("✅ SEPT-OCT BACKTEST COMPLETE!")
        if run_id:
            print(f"📁 Results: runs/{run_id}/")
    except Exception as e:
        print()
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()





