# ORB Strategy Quick Start Guide

## Installation

```bash
# Install dependencies
poetry install

# Or using pip
pip install -r requirements.txt
```

## Running Your First Backtest

### 1. Review the Configuration

The default configuration is in `config/default.yaml`. Key settings:

- **Instruments**: SPY (proxy for ES futures)
- **Date Range**: 2024-01-01 to 2024-03-31
- **OR Duration**: 15 minutes (adaptive disabled for simplicity)
- **Factors**: Relative Volume and Price Action enabled
- **Confluence Scoring**: Requires 2+ factors to pass
- **Trade Management**: Partials enabled (50% at 1.0R, 25% at 1.5R, runner at 2.0R)

### 2. Run a Backtest

```bash
# Basic run (saves trades and equity curve)
poetry run orb-backtest --config config/default.yaml

# With HTML report
poetry run orb-backtest --config config/default.yaml --report

# Disable caching (fetch fresh data)
poetry run orb-backtest --config config/default.yaml --no-cache
```

### 3. View Results

Results are saved to `runs/{run_id}/`:

- `trades.parquet` - All trade details
- `equity_curve.parquet` - R-based equity progression
- `opening_ranges.parquet` - All ORs built
- `metrics.json` - Summary statistics
- `report.html` - Visual report (if --report used)

### 4. Analyze Results

```python
import pandas as pd

# Load trades
trades = pd.read_parquet('runs/{run_id}/trades.parquet')

# Quick analysis
print(f"Total trades: {len(trades)}")
print(f"Win rate: {(trades.realized_r > 0).mean():.1%}")
print(f"Avg R: {trades.realized_r.mean():.2f}")

# View equity curve
equity = pd.read_parquet('runs/{run_id}/equity_curve.parquet')
equity.plot(y='cumulative_r', title='Equity Curve')
```

## Customizing Your Strategy

### Adjusting OR Parameters

```yaml
orb:
  base_minutes: 20  # Use 20-minute OR
  adaptive: true    # Enable adaptive duration
  low_norm_vol: 0.30
  high_norm_vol: 0.90
```

### Enabling More Factors

```yaml
factors:
  vwap:
    enabled: true    # Add VWAP alignment
  adx:
    enabled: true    # Add trend filter
    threshold: 20.0
```

### Adjusting Confluence Requirements

```yaml
scoring:
  base_required: 3      # Need 3 factors minimum
  weak_trend_required: 4  # Need 4 when ADX weak
```

### Changing Risk Management

```yaml
trade:
  stop_mode: atr_capped  # Use ATR-capped stops
  atr_stop_cap_mult: 1.0
  
  partials: false        # Disable partials
  primary_r: 2.0         # Single target at 2.0R
```

## Testing with Different Instruments

### Using Crypto (24/7 Data)

```yaml
instruments:
  BTCUSDT:
    symbol: BTC
    proxy_symbol: BTCUSDT
    data_source: binance
    session_mode: rth
    session_start: "13:30:00"  # Define your "session"
    session_end: "20:00:00"
    timezone: UTC
    tick_size: 0.01
    point_value: 1.0
    enabled: true
```

### Using Synthetic Data (Testing)

```yaml
instruments:
  TEST:
    symbol: TEST
    proxy_symbol: SYN_HIGH_BULL  # High vol bullish
    data_source: synthetic
    # ... rest of config
```

Synthetic symbols:
- `SYN_LOW_*` - Low volatility
- `SYN_MEDIUM_*` - Medium volatility
- `SYN_HIGH_*` - High volatility
- `*_BULL` - Bullish drift
- `*_BEAR` - Bearish drift
- `*_MEAN` - Mean reverting

## Running Tests

```bash
# All tests
poetry run pytest

# Unit tests only
poetry run pytest tests/unit

# With coverage
poetry run pytest --cov=orb_strategy --cov-report=html

# Integration tests (slower)
poetry run pytest -m integration
```

## Troubleshooting

### No Data Returned

**Problem**: "No data returned from Yahoo Finance"

**Solutions**:
1. Yahoo Finance limits intraday data to ~30 days
2. Use shorter date ranges for 1-minute data
3. Consider using Binance for crypto with longer history
4. Use synthetic data for testing

### Configuration Errors

**Problem**: "Config validation failed"

**Solutions**:
1. Check YAML syntax (indentation matters!)
2. Ensure all required fields are present
3. Verify date format: "YYYY-MM-DD"
4. Verify time format: "HH:MM:SS"

### Performance Issues

**Problem**: Backtest runs slowly

**Solutions**:
1. Enable caching (default)
2. Reduce date range
3. Disable factor matrix saving if not needed
4. Use synthetic data for rapid iteration

## Next Steps

1. **Experiment with Parameters**: Use `config/` directory for variants
2. **Add Custom Factors**: Extend `src/orb_strategy/features/factors.py`
3. **Optimize Parameters**: Use Optuna integration (coming soon)
4. **Live Paper Trading**: Integration with broker APIs (Phase 2)

## Getting Help

- Check logs in `logs/` directory
- Review test files for usage examples
- See `Project-Spec.md` for detailed strategy documentation
- Examine `src/orb_strategy/` source code - fully documented

## Example Workflow

```bash
# 1. Create custom config
cp config/default.yaml config/my_strategy.yaml
# Edit my_strategy.yaml

# 2. Run backtest
poetry run orb-backtest -c config/my_strategy.yaml --report

# 3. Review results
open runs/{run_id}/report.html

# 4. Iterate
# Adjust parameters, rerun, compare
```

Happy trading! 🚀
