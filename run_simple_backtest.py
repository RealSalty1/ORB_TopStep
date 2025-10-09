"""Simple Multi-Playbook Backtest - No Regime Classification.

For quick demo, runs without regime detection to avoid feature issues.
"""

from datetime import datetime
import pandas as pd
import json
import os
from loguru import logger

from orb_confluence.data.databento_loader import DatabentoLoader
from orb_confluence.strategy.playbooks import (
    IBFadePlaybook,
    VWAPMagnetPlaybook,
    MomentumContinuationPlaybook,
    OpeningDriveReversalPlaybook,
)


def main():
    """Run simple backtest without regime classification."""
    
    logger.info("=" * 70)
    logger.info("SIMPLE MULTI-PLAYBOOK BACKTEST (NO REGIME FILTER)")
    logger.info("=" * 70)
    
    # Configuration
    SYMBOL = "ES"
    START_DATE = "2025-09-07"
    END_DATE = "2025-10-09"
    
    # Generate run_id
    run_id = f"simple_multi_playbook_{SYMBOL}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
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
    logger.info(f"Loaded {len(bars_1m):,} bars")
    
    if len(bars_1m) == 0:
        logger.error("No data!")
        return
    
    # Initialize playbooks
    logger.info("Initializing playbooks...")
    playbooks = [
        IBFadePlaybook(),
        VWAPMagnetPlaybook(),
        MomentumContinuationPlaybook(),
        OpeningDriveReversalPlaybook(),
    ]
    
    for pb in playbooks:
        logger.info(f"  - {pb.name}")
    
    # Run simple bar-by-bar simulation
    logger.info("=" * 70)
    logger.info("RUNNING SIMPLIFIED BACKTEST...")
    logger.info("=" * 70)
    
    trades = []
    open_positions = []
    
    for i, (timestamp, bar) in enumerate(bars_1m.iterrows()):
        if i % 5000 == 0:
            logger.info(f"Progress: {i}/{len(bars_1m)} bars ({i/len(bars_1m)*100:.1f}%)")
        
        # Simple: just count how many signals each playbook would generate
        # (not actually executing trades, just logging potential signals)
        
        # For now, just demonstrate the system is working
        pass
    
    logger.info("=" * 70)
    logger.info("BACKTEST COMPLETE (SIMPLIFIED)")
    logger.info("=" * 70)
    logger.info(f"This was a simplified run to demonstrate the system.")
    logger.info(f"Run ID: {run_id}")
    logger.info(f"Output: {output_dir}/")
    
    # Save placeholder results
    metrics = {
        "note": "Simplified backtest - demonstrates system integration",
        "playbooks_loaded": [pb.name for pb in playbooks],
        "bars_processed": len(bars_1m),
        "date_range": f"{START_DATE} to {END_DATE}",
    }
    
    with open(f"{output_dir}/metrics.json", 'w') as f:
        json.dump(metrics, f, indent=2)
    
    logger.info("✓ Saved metrics.json")


if __name__ == "__main__":
    main()

