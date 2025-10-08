# run_backtest.py - End-to-End Backtest Runner

## Overview

`run_backtest.py` is a comprehensive CLI script that runs complete end-to-end backtests with multi-symbol support, data caching, and rich output formatting.

**Features:**
- ✅ Multi-symbol backtesting
- ✅ Data caching for faster reruns
- ✅ Automatic data fetching (Yahoo Finance or synthetic)
- ✅ OR window validation (optional)
- ✅ Per-symbol and aggregated results
- ✅ Rich console output with progress bars
- ✅ Comprehensive result saving (parquet, CSV, JSON)
- ✅ HTML report generation (optional)
- ✅ Detailed logging

---

## Installation

Ensure all dependencies are installed:

```bash
# Install with poetry
poetry install

# Or with pip
pip install -r requirements.txt

# Required packages for run_backtest.py:
pip install rich loguru pandas
```

---

## Basic Usage

### Command Structure

```bash
python run_backtest.py --symbols SYMBOL1 SYMBOL2 ... --start YYYY-MM-DD --end YYYY-MM-DD [OPTIONS]
```

### Required Arguments

| Argument | Description | Example |
|----------|-------------|---------|
| `--symbols` | Space-separated list of symbols | `--symbols SPY QQQ` |
| `--start` | Start date (YYYY-MM-DD) | `--start 2024-01-02` |
| `--end` | End date (YYYY-MM-DD) | `--end 2024-01-31` |

### Optional Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--config PATH` | Custom config file | `defaults.yaml` |
| `--cache` | Enable data caching | Disabled |
| `--cache-dir DIR` | Cache directory | `cache/` |
| `--report` | Generate HTML reports | Disabled |
| `--output-dir DIR` | Output directory | `runs/` |
| `--synthetic` | Use synthetic data | Disabled |
| `--validate-or` | Validate OR window | Disabled |
| `--verbose, -v` | Verbose output | Disabled |

---

## Examples

### 1. Single Symbol, Default Config

```bash
python run_backtest.py --symbols SPY --start 2024-01-02 --end 2024-01-31
```

**Output:**
- Fetches SPY data from Yahoo Finance
- Runs backtest with default configuration
- Saves results to `runs/backtest_YYYYMMDD_HHMMSS/`
- Prints summary table

### 2. Multiple Symbols

```bash
python run_backtest.py --symbols SPY QQQ IWM --start 2024-01-02 --end 2024-03-31
```

**Output:**
- Fetches data for 3 symbols
- Runs separate backtest for each
- Aggregates results
- Saves per-symbol and combined results

### 3. With Data Caching

```bash
python run_backtest.py --symbols SPY --start 2024-01-02 --end 2024-06-30 --cache
```

**Benefits:**
- First run: Fetches and caches data
- Subsequent runs: Loads from cache (much faster)
- Cached files: `cache/SPY_2024-01-02_2024-06-30.parquet`

### 4. Custom Configuration

```bash
python run_backtest.py --symbols SPY --start 2024-01-02 --end 2024-03-31 --config my_config.yaml
```

**my_config.yaml:**
```yaml
orb:
  base_minutes: 30
  adaptive: true

trade:
  stop_mode: atr_capped
  partials: true
  t1_r: 1.0
  runner_r: 3.0

governance:
  max_signals_per_day: 2
  lockout_after_losses: 1
  max_daily_loss_r: 3.0
```

### 5. Synthetic Data (Testing)

```bash
python run_backtest.py --symbols SPY --start 2024-01-02 --end 2024-01-10 --synthetic
```

**Use case:** Fast testing without API calls

### 6. With OR Validation

```bash
python run_backtest.py --symbols SPY QQQ --start 2024-01-02 --end 2024-03-31 --validate-or
```

**Behavior:** Validates OR window for continuous minute coverage (logs warnings if invalid)

### 7. Full Production Run

```bash
python run_backtest.py \
  --symbols SPY QQQ IWM \
  --start 2024-01-02 \
  --end 2024-12-31 \
  --config production.yaml \
  --cache \
  --report \
  --validate-or \
  --verbose
```

**Features:**
- Multiple symbols
- Custom config
- Data caching
- HTML reports
- OR validation
- Verbose logging

---

## Output Structure

### Directory Layout

```
runs/
└── backtest_20241002_153045/
    ├── SPY_trades.parquet         # Per-symbol trades
    ├── SPY_metrics.json           # Per-symbol metrics
    ├── SPY_equity.parquet         # Per-symbol equity curve
    ├── QQQ_trades.parquet
    ├── QQQ_metrics.json
    ├── QQQ_equity.parquet
    ├── all_trades.parquet         # Combined trades
    ├── all_trades.csv             # Combined trades (CSV)
    ├── combined_equity.parquet    # Combined equity curve
    ├── config.json                # Run configuration
    └── SPY_report.html            # HTML reports (if --report)
```

### Console Output

**Example:**

```
╭──────────────────────────────────────────────╮
│ ORB Confluence Strategy - Backtest Runner   │
╰──────────────────────────────────────────────╯

Loading configuration...
Run ID: backtest_20241002_153045

⠋ Fetching data... ━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 2/2

Data fetched for 2 symbols

⠋ Running backtests... ━━━━━━━━━━━━━━━━━━━━━━ 100% 2/2

Completed 2 backtests

Aggregating results...

╭─────────────────── Backtest Summary ───────────────────╮
│                                                         │
│                  Per-Symbol Results                     │
│ ╭─────────┬────────┬──────────┬──────────┬────────╮   │
│ │ Symbol  │ Trades │ Win Rate │ Total R  │ Sharpe │   │
│ ├─────────┼────────┼──────────┼──────────┼────────┤   │
│ │ SPY     │     25 │   60.0%  │   5.20R  │  1.85  │   │
│ │ QQQ     │     18 │   55.6%  │   3.80R  │  1.52  │   │
│ ╰─────────┴────────┴──────────┴──────────┴────────╯   │
│                                                         │
│                  Aggregated Results                     │
│ ╭────────────────────┬─────────╮                       │
│ │ Total Symbols      │    2    │                       │
│ │ Total Trades       │   43    │                       │
│ │ Total R            │ 9.00R   │                       │
│ │ Average R per Trade│ 0.209R  │                       │
│ ╰────────────────────┴─────────╯                       │
╰─────────────────────────────────────────────────────────╯

╭────────────────── Backtest Complete ──────────────────╮
│                                                        │
│ ✓ Results saved to: runs/backtest_20241002_153045    │
│ ✓ Run ID: backtest_20241002_153045                   │
│                                                        │
│ View results in Streamlit dashboard:                  │
│   streamlit run streamlit_app.py                      │
╰────────────────────────────────────────────────────────╯
```

---

## Workflow

### Step-by-Step Process

1. **Load Configuration**
   - Loads config from `--config` file or defaults
   - Validates with Pydantic
   - Logs configuration summary

2. **Fetch/Cache Data**
   - For each symbol:
     - Check cache (if `--cache` enabled)
     - Fetch from Yahoo Finance or generate synthetic
     - Save to cache (if `--cache` enabled)
   - Progress bar shows fetching status

3. **Run Backtests**
   - For each symbol:
     - Optionally validate OR window (if `--validate-or`)
     - Initialize EventLoopBacktest
     - Run bar-by-bar simulation
     - Compute metrics and equity curve
   - Progress bar shows backtest progress

4. **Aggregate Results**
   - Combine trades from all symbols
   - Merge equity curves
   - Calculate aggregate statistics

5. **Save Results**
   - Per-symbol files (trades, metrics, equity)
   - Combined files (all trades, combined equity)
   - Configuration snapshot
   - Optional HTML reports

6. **Print Summary**
   - Per-symbol table (trades, win rate, R, Sharpe)
   - Aggregated statistics
   - Output directory location

---

## Integration with Dashboard

After running the backtest:

```bash
# View results in Streamlit
streamlit run streamlit_app.py
```

The dashboard will:
- Automatically detect new run in `runs/` directory
- Load trades, equity, and metrics
- Display interactive charts and tables
- Allow filtering and analysis

---

## Integration with REST API

Start the API server:

```bash
uvicorn api_server:app --reload
```

Query results:

```bash
# List runs
curl http://localhost:8000/api/runs

# Get trades
curl "http://localhost:8000/api/trades?run_id=backtest_20241002_153045"

# Get metrics
curl "http://localhost:8000/api/metrics/core?run_id=backtest_20241002_153045"
```

---

## Performance Tips

### 1. Use Data Caching

```bash
# First run (slow - fetches data)
python run_backtest.py --symbols SPY --start 2024-01-02 --end 2024-12-31 --cache

# Subsequent runs (fast - uses cache)
python run_backtest.py --symbols SPY --start 2024-01-02 --end 2024-12-31 --cache --config test.yaml
```

**Speedup:** 10-100x faster on reruns

### 2. Use Synthetic Data for Testing

```bash
python run_backtest.py --symbols SPY QQQ IWM --start 2024-01-02 --end 2024-03-31 --synthetic
```

**Benefit:** No API calls, deterministic results

### 3. Run in Verbose Mode for Debugging

```bash
python run_backtest.py --symbols SPY --start 2024-01-02 --end 2024-01-31 --verbose
```

**Output:** Detailed logs to console and `backtest_run.log`

---

## Troubleshooting

### No Data Fetched

**Symptom:** "No data fetched for SYMBOL"

**Solutions:**
1. Check date range (must be trading days)
2. Verify symbol is valid (Yahoo Finance format)
3. Check internet connection
4. Try with `--synthetic` flag for testing

### No Trades Generated

**Symptom:** "No trades generated" for all symbols

**Solutions:**
1. Check configuration (thresholds too strict?)
2. Review logs for OR validation failures
3. Verify data quality (gaps in minute data?)
4. Try different date range

### Cache Issues

**Symptom:** Old data from cache

**Solution:** Delete cache and refetch

```bash
rm -rf cache/
python run_backtest.py --symbols SPY --start 2024-01-02 --end 2024-01-31 --cache
```

---

## Advanced Usage

### Batch Processing Multiple Configs

```bash
# Create script
for config in configs/*.yaml; do
    python run_backtest.py \
        --symbols SPY \
        --start 2024-01-02 \
        --end 2024-12-31 \
        --config "$config" \
        --cache
done
```

### Parallel Processing (Multiple Symbols)

The script runs symbols sequentially. For parallel processing, use:

```bash
# Terminal 1
python run_backtest.py --symbols SPY --start 2024-01-02 --end 2024-12-31 --cache

# Terminal 2
python run_backtest.py --symbols QQQ --start 2024-01-02 --end 2024-12-31 --cache

# Terminal 3
python run_backtest.py --symbols IWM --start 2024-01-02 --end 2024-12-31 --cache
```

---

## Logging

### Log Files

- **Console**: Real-time output with Rich formatting
- **File**: `backtest_run.log` (detailed debug logs)

### Log Levels

- **Default**: INFO level (key events)
- **Verbose**: DEBUG level (all details)

```bash
# Verbose logging
python run_backtest.py --symbols SPY --start 2024-01-02 --end 2024-01-31 --verbose
```

---

## Best Practices

1. **Always use `--cache` for development**: Speeds up iterative testing
2. **Validate OR windows in production**: Use `--validate-or` to ensure data quality
3. **Start with short date ranges**: Test with 1-2 months before full year
4. **Use custom configs for experimentation**: Keep defaults.yaml clean
5. **Enable HTML reports for important runs**: Use `--report` for documentation
6. **Review logs after each run**: Check `backtest_run.log` for issues

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (config load, data fetch, or backtest failure) |

---

**Script Version**: 1.0  
**Last Updated**: 2024  
**Status**: Production-Ready ✅

**Happy backtesting! 🚀📊**
