"""Run Multi-Playbook Strategy Backtest.

Simple script to demonstrate the complete multi-playbook trading system.

Usage:
    python run_multi_playbook_backtest.py
"""

from datetime import datetime
import pandas as pd
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
    """Run multi-playbook backtest."""
    
    logger.info("=" * 60)
    logger.info("MULTI-PLAYBOOK STRATEGY BACKTEST")
    logger.info("=" * 60)
    
    # Configuration
    SYMBOL = "ES"
    ACCOUNT_SIZE = 100000
    BASE_RISK = 0.01  # 1% per trade
    START_DATE = "2024-01-01"
    END_DATE = "2024-12-31"
    
    # Load data
    logger.info(f"Loading {SYMBOL} 1m data...")
    loader_1m = DatabentoLoader(symbol=SYMBOL, data_dir="data_cache/databento_1m")
    bars_1m = loader_1m.load_data()
    logger.info(f"Loaded {len(bars_1m)} bars")
    
    # Initialize playbooks
    logger.info("Initializing playbooks...")
    playbooks = [
        IBFadePlaybook(
            ib_duration_minutes=60,
            aer_threshold=0.65,
            ib_extension_factor=1.5,
        ),
        VWAPMagnetPlaybook(
            vwap_band_multiplier=1.5,
            vwap_band_window=20,
            rejection_velocity_threshold=0.02,
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
        config=config,
        start_date=START_DATE,
        end_date=END_DATE,
    )
    
    # Run backtest
    logger.info("=" * 60)
    logger.info("RUNNING BACKTEST...")
    logger.info("=" * 60)
    
    results = backtest.run()
    
    # Display results
    logger.info("=" * 60)
    logger.info("RESULTS")
    logger.info("=" * 60)
    
    print(results.summary())
    
    # Save results
    output_dir = f"runs/multi_playbook_{SYMBOL}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    logger.info(f"Saving results to {output_dir}/...")
    
    import os
    os.makedirs(output_dir, exist_ok=True)
    
    # Save equity curve
    results.equity_curve.to_csv(f"{output_dir}/equity_curve.csv")
    logger.info(f"  - equity_curve.csv")
    
    # Save trades
    trades_df = pd.DataFrame([
        {
            'playbook': t.playbook_name,
            'direction': t.direction.value,
            'entry_time': t.entry_time,
            'exit_time': t.exit_time,
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
    trades_df.to_csv(f"{output_dir}/trades.csv", index=False)
    logger.info(f"  - trades.csv ({len(trades_df)} trades)")
    
    # Save daily stats
    results.daily_stats.to_csv(f"{output_dir}/daily_stats.csv")
    logger.info(f"  - daily_stats.csv")
    
    # Save metrics
    import json
    with open(f"{output_dir}/metrics.json", 'w') as f:
        json.dump(results.metrics, f, indent=2, default=str)
    logger.info(f"  - metrics.json")
    
    # Save playbook stats
    with open(f"{output_dir}/playbook_stats.json", 'w') as f:
        json.dump(results.playbook_stats, f, indent=2)
    logger.info(f"  - playbook_stats.json")
    
    logger.info("=" * 60)
    logger.info("BACKTEST COMPLETE!")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

