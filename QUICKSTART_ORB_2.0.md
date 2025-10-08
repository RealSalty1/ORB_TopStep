# ORB 2.0 Quick Start Guide

**Version**: 1.0  
**Date**: October 8, 2025

---

## 📋 Overview

ORB 2.0 transforms the original single-tactic ORB breakout system into a **multi-playbook, state-aware, probability-gated framework**. This guide gets you started quickly.

---

## 🚀 Installation

```bash
# Navigate to project
cd /path/to/ORB(15m)

# Install dependencies (if not already)
pip install -r requirements.txt

# Run tests to verify
pytest orb_confluence/tests/ -v
```

---

## 🎯 Core Concepts

### 1. **Dual OR Layers**
- **Micro OR** (5-7 min): Early state detection
- **Primary OR** (10-20 min): Adaptive based on volatility

### 2. **Auction States** (6 types)
- `INITIATIVE`: Strong directional drive
- `BALANCED`: Two-sided, rotational
- `COMPRESSION`: Narrow, low energy
- `GAP_REV`: Gap failing to extend
- `INVENTORY_FIX`: Overnight correction
- `MIXED`: Ambiguous

### 3. **Playbooks** (Tactics)
- **PB1**: Classic ORB (refined with state awareness)
- **PB2**: OR Failure Fade (counter-trend)
- **PB3**: Pullback Continuation (flag breakouts)
- *More to come*: Compression expansion, gap reversion, spread alignment

### 4. **Risk Management**
- **Two-Phase Stops**: Statistical → Structural → Runner
- **Salvage Abort**: Exit early on MFE give-backs
- **Context Exclusion**: Filter low-expectancy setups

---

## 📝 Basic Usage

### Example 1: Build Dual OR

```python
from datetime import datetime
from orb_confluence.features import DualORBuilder

# Initialize builder
or_builder = DualORBuilder(
    start_ts=datetime(2024, 1, 2, 14, 30),
    micro_minutes=5,
    primary_base_minutes=15,
    atr_14=2.5,  # Recent ATR
    atr_60=3.0,  # Longer ATR for regime
)

# Feed bars during OR period
for bar in bars:
    or_builder.update(bar)
    micro_done, primary_done = or_builder.finalize_if_due(bar["timestamp_utc"])

# Get OR state
dual_or = or_builder.state()
print(f"Micro: {dual_or.micro_width:.2f}, Primary: {dual_or.primary_width:.2f}")
print(f"Width ratio: {dual_or.width_ratio:.2f}")
```

### Example 2: Classify Auction State

```python
from orb_confluence.features import AuctionMetricsBuilder
from orb_confluence.states import classify_auction_state

# Build auction metrics
metrics_builder = AuctionMetricsBuilder(
    start_ts=datetime(2024, 1, 2, 14, 30),
    atr_14=2.5,
    adr_20=50.0,
    prior_high=5010.0,
    prior_low=4990.0,
    prior_close=5000.0,
)

for bar in or_bars:
    metrics_builder.add_bar(bar)

metrics = metrics_builder.compute()

# Classify state
classification = classify_auction_state(metrics, dual_or)

print(f"State: {classification.state}")
print(f"Confidence: {classification.confidence:.2f}")
print(f"Reason: {classification.reason}")
```

### Example 3: Generate Signals from Playbook

```python
from orb_confluence.playbooks import ORBRefinedPlaybook

# Create playbook
playbook = ORBRefinedPlaybook(config={
    "buffer": {
        "base": 0.75,
        "vol_alpha": 0.35,
        "rotation_penalty": 0.10,
        "min": 0.50,
        "max": 2.00
    }
})

# Build context
context = {
    "auction_state": "INITIATIVE",
    "or_primary_high": 5010.0,
    "or_primary_low": 5000.0,
    "or_primary_finalized": True,
    "or_primary_valid": True,
    "current_price": 5012.5,
    "atr_14": 2.5,
    "timestamp": datetime.now(),
    "rotations": 1,
    "recent_return_std": 0.02,
    "context_excluded": False,
}

# Check eligibility
if playbook.is_eligible(context):
    signals = playbook.generate_signals(context)
    for signal in signals:
        print(f"Signal: {signal.direction} @ {signal.entry_price:.2f}")
        print(f"  Stop: {signal.initial_stop:.2f}")
        print(f"  Exit mode: {signal.exit_mode.mode}")
```

### Example 4: Manage Trade Risk

```python
from orb_confluence.risk import TwoPhaseStopManager, SalvageManager

# Initialize stop manager
stop_mgr = TwoPhaseStopManager(
    direction="long",
    entry_price=5000.0,
    initial_risk=5.0,
    phase1_stop_distance=4.0,
    phase2_trigger_r=0.6,
    structural_anchor=4995.0,
)

# Initialize salvage manager
salvage_mgr = SalvageManager(
    direction="long",
    entry_price=5000.0,
    initial_risk=5.0,
    initial_stop=4996.0,
)

# On each bar
for bar in trade_bars:
    current_price = bar["close"]
    current_mfe_r = (current_price - 5000.0) / 5.0  # Simple calc
    current_r = current_mfe_r
    
    # Check salvage first
    salvage_event = salvage_mgr.evaluate(
        current_price=current_price,
        current_mfe_r=current_mfe_r,
        current_r=current_r,
        timestamp=bar["timestamp_utc"],
    )
    
    if salvage_event:
        print(f"SALVAGE EXIT: {salvage_event}")
        break
    
    # Update stop
    stop_update = stop_mgr.update(
        current_price=current_price,
        current_mfe_r=current_mfe_r,
        timestamp=bar["timestamp_utc"],
    )
    
    if stop_update:
        print(f"Stop updated: {stop_update}")
    
    # Check stop hit
    if stop_mgr.check_stop_hit(current_price):
        print(f"STOP HIT at {current_price:.2f}")
        break
```

### Example 5: Context Exclusion

```python
from orb_confluence.states import ContextExclusionMatrix
import pandas as pd

# Load historical trades
trades_df = pd.read_parquet("historical_trades.parquet")

# Fit matrix
matrix = ContextExclusionMatrix(
    min_trades_per_cell=30,
    expectancy_threshold=-0.25,
)

matrix.fit(
    trades_df,
    or_width_norm_col="or_width_norm",
    breakout_delay_col="breakout_delay_minutes",
    volume_quality_col="volume_quality_score",
    auction_state_col="auction_state",
    gap_type_col="gap_type",
    realized_r_col="realized_r",
)

# Export analysis
matrix.save("context_exclusion_matrix.csv")

# Check if new trade should be taken
signature = matrix.create_signature(
    or_width_norm=0.8,
    breakout_delay=12.5,
    volume_quality=0.75,
    auction_state="INITIATIVE",
    gap_type="NO_GAP",
)

if matrix.is_excluded(signature):
    print(f"Context excluded: {matrix.get_exclusion_reason(signature)}")
else:
    print("Context OK, can take trade")
```

---

## 🧪 Running Tests

```bash
# Run all tests
pytest orb_confluence/tests/ -v

# Run specific module tests
pytest orb_confluence/tests/test_or_layers.py -v
pytest orb_confluence/tests/test_auction_metrics.py -v
pytest orb_confluence/tests/test_auction_state.py -v

# Run with coverage
pytest orb_confluence/tests/ --cov=orb_confluence --cov-report=html
```

---

## 📊 Configuration

Create a YAML config file:

```yaml
# config/orb_2.0.yaml

instruments:
  ES:
    enabled: true

or:
  micro_minutes: 5
  adaptive:
    base: 15
    min: 10
    max: 20
    low_vol_threshold: 0.35
    high_vol_threshold: 0.85

auction_state:
  drive_energy_threshold: 0.55
  rotations_initiative_max: 2
  compression_width_quantile: 0.20
  volume_z_initiative: 1.0

playbooks:
  PB1_ORB:
    enabled: true
    buffer:
      base: 0.75
      vol_alpha: 0.35
      rotation_penalty: 0.10
      min: 0.50
      max: 2.00
    phase2_trigger_r: 0.6
  
  PB2_FAILURE_FADE:
    enabled: true
    wick_ratio_min: 0.55
    volume_fade_threshold: 0.8
    reenter_mid: true
  
  PB3_PULLBACK_CONTINUATION:
    enabled: true
    impulse_threshold_r: 0.8
    impulse_time_bars: 15

risk:
  phase1_stop_pct_mae_winner: 0.80
  salvage:
    trigger_mfe_r: 0.4
    retrace_threshold: 0.65
    confirmation_bars: 6

context_exclusion:
  min_trades_cell: 30
  expectancy_threshold: -0.25
```

Load config:

```python
from orb_confluence.config import loader

config = loader.load_config("config/orb_2.0.yaml")
```

---

## 🔍 Debugging Tips

### Enable Detailed Logging

```python
from loguru import logger
import sys

# Configure logger
logger.remove()
logger.add(sys.stderr, level="DEBUG")
```

### Inspect Feature Table

```python
from orb_confluence.features import FeatureTableBuilder

builder = FeatureTableBuilder(instrument="ES", session_date="2024-01-02")
# ... populate features ...
df = builder.to_dataframe()

print(df.head())
print(df.info())
```

### Analyze MFE/MAE Distributions

```python
from orb_confluence.analytics.mfe_mae import compute_mfe_mae_distribution

distribution = compute_mfe_mae_distribution(trade_analyses)

print(f"Winner MAE 80th: {distribution.mae_winners_80th:.2f}R")
print(f"Salvage candidate rate: {distribution.salvage_candidate_rate:.1%}")
```

---

## 📈 Next Steps

1. **Integrate with backtest engine**: Connect to existing event loop
2. **Add remaining playbooks**: PB4-PB6 (compression, gap reversion, spread)
3. **Build exit architecture**: Trailing modes, partial manager
4. **Train probability model**: Extension probability predictor
5. **Run OOS validation**: Walk-forward testing

---

## 🆘 Troubleshooting

### Common Issues

**Issue**: `ImportError: cannot import name 'DualORBuilder'`
- **Fix**: Ensure you're in the project root and orb_confluence is in Python path

**Issue**: OR not finalizing
- **Fix**: Check timestamps - bars must be >= end_ts

**Issue**: No signals generated
- **Fix**: Check eligibility conditions (auction state, context exclusion)

**Issue**: Stop inversion (stop price wrong side of entry)
- **Fix**: Verify direction string ("long" vs "short", lowercase)

---

## 📚 Additional Resources

- **Full Specification**: `10_07_implementation.md`
- **Implementation Status**: `ORB_2.0_IMPLEMENTATION_STATUS.md`
- **API Documentation**: Module docstrings
- **Tests**: `orb_confluence/tests/` for usage examples

---

## 🤝 Contributing

When adding new features:
1. Follow existing module structure
2. Add comprehensive docstrings
3. Write tests (unit + integration)
4. Update implementation status doc
5. Add usage examples

---

**Last Updated**: October 8, 2025  
**Questions?** See full specification or module docstrings

