"""Run Multi-Playbook Backtest for Streamlit Dashboard.

Generates results compatible with existing Streamlit visualization.
"""

from datetime import datetime
import pandas as pd
import json
import os
from loguru import logger

from orb_confluence.data.databento_loader import DatabentoLoader
from orb_confluence.strategy.multi_playbook_strategy import MultiPlaybookStrategy
from orb_confluence.strategy.playbooks import (
    IBFadePlaybook,
    VWAPMagnetPlaybook,
    MomentumContinuationPlaybook,
    OpeningDriveReversalPlaybook,
)
from orb_confluence.backtest.multi_playbook_backtest import (
    MultiPlaybookBacktest,
    BacktestConfig,
)


def main():
    """Run multi-playbook backtest with Streamlit-compatible output."""
    
    logger.info("=" * 70)
    logger.info("MULTI-PLAYBOOK STRATEGY BACKTEST - STREAMLIT FORMAT")
    logger.info("=" * 70)
    
    # Configuration
    SYMBOL = "ES"
    ACCOUNT_SIZE = 100000
    BASE_RISK = 0.01  # 1% per trade
    START_DATE = "2025-09-07"  # September 7, 2025
    END_DATE = "2025-10-09"    # Today
    
    # Generate run_id
    run_id = f"multi_playbook_{SYMBOL}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_dir = f"runs/{run_id}"
    
    logger.info(f"Run ID: {run_id}")
    logger.info(f"Date Range: {START_DATE} to {END_DATE}")
    logger.info(f"Output: {output_dir}/")
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Load data
    logger.info(f"Loading {SYMBOL} 1m data...")
    loader_1m = DatabentoLoader(data_directory="data_cache/databento_1m")
    bars_1m = loader_1m.load(symbol=SYMBOL, start_date=START_DATE, end_date=END_DATE)
    logger.info(f"Loaded {len(bars_1m):,} bars in range {START_DATE} to {END_DATE}")
    
    if len(bars_1m) == 0:
        logger.error("No data in date range!")
        return
    
    # Create daily bars from 1m data
    logger.info("Creating daily bars from 1m data...")
    # Ensure index is DatetimeIndex
    if not isinstance(bars_1m.index, pd.DatetimeIndex):
        bars_1m.index = pd.to_datetime(bars_1m.index)
    
    bars_daily = bars_1m.resample('D').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
    }).dropna()
    logger.info(f"Created {len(bars_daily)} daily bars")
    
    # Initialize playbooks
    logger.info("Initializing playbooks...")
    playbooks = [
        IBFadePlaybook(
            ib_minutes=60,
            extension_threshold=1.5,
            max_aer=0.65,
        ),
        VWAPMagnetPlaybook(
            band_multiplier=2.0,
            min_rejection_velocity=0.3,
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
    
    logger.info(f"Loaded {len(playbooks)} playbooks:")
    for pb in playbooks:
        logger.info(f"  - {pb.name} ({pb.playbook_type})")
    
    # Initialize strategy
    logger.info(f"Initializing strategy (account: ${ACCOUNT_SIZE:,.0f})...")
    strategy = MultiPlaybookStrategy(
        playbooks=playbooks,
        account_size=ACCOUNT_SIZE,
        base_risk=BASE_RISK,
        max_simultaneous_positions=3,
        target_volatility=0.01,
        max_portfolio_heat=0.05,
        enable_signal_arbitration=True,
        enable_correlation_weighting=True,
    )
    
    # Initialize backtest
    logger.info("Initializing backtest...")
    config = BacktestConfig(
        initial_capital=ACCOUNT_SIZE,
        commission_per_contract=2.50,
        slippage_ticks=1.0,
        tick_size=0.25,
        tick_value=12.50,
        point_value=50.0,
        close_eod=True,
    )
    
    backtest = MultiPlaybookBacktest(
        strategy=strategy,
        bars_1m=bars_1m,
        bars_daily=bars_daily,
        config=config,
        start_date=None,  # Already filtered
        end_date=None,    # Already filtered
    )
    
    # Run backtest
    logger.info("=" * 70)
    logger.info("RUNNING BACKTEST...")
    logger.info("=" * 70)
    
    results = backtest.run()
    
    # Display results
    logger.info("=" * 70)
    logger.info("RESULTS")
    logger.info("=" * 70)
    
    print(results.summary())
    
    # Save in Streamlit-compatible format
    logger.info("=" * 70)
    logger.info(f"SAVING RESULTS (Streamlit format): {output_dir}/")
    logger.info("=" * 70)
    
    # 1. Save metrics.json (compatible with existing format)
    metrics = {
        "total_trades": results.metrics['total_trades'],
        "winning_trades": results.metrics['winning_trades'],
        "losing_trades": results.metrics['losing_trades'],
        "win_rate": results.metrics['win_rate'],
        "expectancy": results.metrics['expectancy_r'],
        "cumulative_r": results.metrics['total_r'],
        "avg_winner": results.metrics['avg_win_r'],
        "avg_loser": results.metrics['avg_loss_r'],
        "max_win": results.metrics['largest_win_r'],
        "max_loss": results.metrics['largest_loss_r'],
        "profit_factor": results.metrics['profit_factor'],
        "sharpe_ratio": results.metrics['sharpe_ratio'],
        "sortino_ratio": results.metrics['sortino_ratio'],
        "max_drawdown": results.metrics['max_drawdown'],
        "total_return": results.metrics['total_return'],
        "cagr": results.metrics['cagr'],
        "trades_by_playbook": {
            pb: stats['count'] 
            for pb, stats in results.playbook_stats.items()
        },
    }
    
    with open(f"{output_dir}/metrics.json", 'w') as f:
        json.dump(metrics, f, indent=2)
    logger.info(f"  ✓ metrics.json")
    
    # 2. Save equity curve
    equity_df = pd.DataFrame({
        'timestamp': results.equity_curve.index,
        'equity': results.equity_curve.values,
    })
    equity_df.to_parquet(f"{output_dir}/{SYMBOL}_equity.parquet")
    equity_df.to_csv(f"{output_dir}/{SYMBOL}_equity.csv", index=False)
    logger.info(f"  ✓ {SYMBOL}_equity.parquet")
    logger.info(f"  ✓ {SYMBOL}_equity.csv")
    
    # 2b. Save price data for charts (bars_1m)
    # Fix: Set index to timestamp_utc for proper chart display
    bars_to_save = bars_1m.copy()
    if 'timestamp_utc' in bars_to_save.columns:
        bars_to_save.index = pd.to_datetime(bars_to_save['timestamp_utc'])
        bars_to_save = bars_to_save.drop(columns=['timestamp_utc'])
    bars_to_save.to_parquet(f"{output_dir}/{SYMBOL}_bars_1m.parquet")
    logger.info(f"  ✓ {SYMBOL}_bars_1m.parquet ({len(bars_to_save)} bars)")
    
    # 3. Save trades
    if len(results.trades) > 0:
        trades_df = pd.DataFrame([
            {
                'entry_time': t.entry_time,
                'exit_time': t.exit_time,
                'playbook': t.playbook_name,
                'direction': t.direction.value,
                'entry_price': t.entry_price,
                'exit_price': t.exit_price,
                'size': t.size,
                'r_multiple': t.r_multiple,
                'pnl': t.pnl,
                'bars_in_trade': t.bars_in_trade,
                'exit_reason': t.exit_reason,
                'mfe': t.mfe,
                'mae': t.mae,
            }
            for t in results.trades
        ])
        
        trades_df.to_parquet(f"{output_dir}/{SYMBOL}_trades.parquet")
        trades_df.to_csv(f"{output_dir}/{SYMBOL}_trades.csv", index=False)
        logger.info(f"  ✓ {SYMBOL}_trades.parquet ({len(trades_df)} trades)")
        logger.info(f"  ✓ {SYMBOL}_trades.csv")
    else:
        logger.warning("  ! No trades to save")
    
    # 4. Save config
    config_data = {
        "symbol": SYMBOL,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "account_size": ACCOUNT_SIZE,
        "base_risk": BASE_RISK,
        "playbooks": [pb.name for pb in playbooks],
        "max_simultaneous_positions": 3,
        "target_volatility": 0.01,
        "max_portfolio_heat": 0.05,
        "commission_per_contract": config.commission_per_contract,
        "slippage_ticks": config.slippage_ticks,
    }
    
    with open(f"{output_dir}/config.json", 'w') as f:
        json.dump(config_data, f, indent=2, default=str)
    logger.info(f"  ✓ config.json")
    
    # 5. Save detailed metrics for reference
    with open(f"{output_dir}/detailed_metrics.json", 'w') as f:
        json.dump(results.metrics, f, indent=2, default=str)
    logger.info(f"  ✓ detailed_metrics.json")
    
    # 6. Save playbook stats
    with open(f"{output_dir}/playbook_stats.json", 'w') as f:
        json.dump(results.playbook_stats, f, indent=2)
    logger.info(f"  ✓ playbook_stats.json")
    
    # 7. Save daily stats
    results.daily_stats.to_csv(f"{output_dir}/daily_stats.csv")
    logger.info(f"  ✓ daily_stats.csv")
    
    logger.info("=" * 70)
    logger.info("BACKTEST COMPLETE!")
    logger.info("=" * 70)
    logger.info(f"Run ID: {run_id}")
    logger.info(f"Output: {output_dir}/")
    logger.info("")
    logger.info("To view in Streamlit:")
    logger.info(f"  1. Look for run: {run_id}")
    logger.info(f"  2. Files are in: {output_dir}/")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()

