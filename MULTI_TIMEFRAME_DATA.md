# Multi-Timeframe Data for ES

## Overview

Successfully created resampled data from 1-minute Databento data for ES futures across multiple timeframes.

## Data Files Created

All files are located in `data_cache/` with the following structure:

| Timeframe | File Path | Bars | Size | Date Range |
|-----------|-----------|------|------|------------|
| 1 minute | `databento_1m/ES_1m.json` | 1,767,905 | 278 MB | 2020-10-06 to 2025-10-05 |
| 5 minutes | `databento_5m/ES_5m.json` | 353,695 | 58 MB | 2020-10-06 to 2025-10-05 |
| 15 minutes | `databento_15m/ES_15m.json` | 117,899 | 19 MB | 2020-10-06 to 2025-10-05 |
| 30 minutes | `databento_30m/ES_30m.json` | 59,046 | 10 MB | 2020-10-06 to 2025-10-05 |
| 1 hour | `databento_1h/ES_1h.json` | 29,530 | 5 MB | 2020-10-06 to 2025-10-05 |

## Data Format

Each JSON file contains:

```json
{
  "symbol": "ES",
  "interval": "15m",
  "bar_count": 117899,
  "start_date": "2020-10-06",
  "end_date": "2025-10-05",
  "data": [
    {
      "timestamp": "2020-10-06T00:00:00+00:00",
      "open": 3389.5,
      "high": 3394.75,
      "low": 3388.5,
      "close": 3393.5,
      "volume": 3837
    },
    ...
  ]
}
```

## Resampling Method

OHLCV bars are resampled using proper aggregation:
- **Open**: First value in the period
- **High**: Maximum value in the period
- **Low**: Minimum value in the period
- **Close**: Last value in the period
- **Volume**: Sum of all volume in the period

## Usage

### Loading Data with DatabentoLoader

The `DatabentoLoader` can be updated to load different timeframes:

```python
from orb_confluence.data.databento_loader import DatabentoLoader

# Load 15m data
loader = DatabentoLoader("data_cache/databento_15m")
bars = loader.load("ES", start_date="2025-01-01", end_date="2025-10-07")

# Load 1h data
loader = DatabentoLoader("data_cache/databento_1h")
bars = loader.load("ES", start_date="2025-01-01", end_date="2025-10-07")
```

### Regenerating Data

To regenerate the multi-timeframe data:

```bash
python scripts/create_multi_timeframe_data.py
```

## Benefits for Strategy Development

1. **Multi-Timeframe Analysis**: Can now analyze price action across multiple timeframes simultaneously
2. **Trend Confirmation**: Use higher timeframes (1h, 30m) for trend direction
3. **Entry Refinement**: Use lower timeframes (5m, 1m) for precise entries
4. **Volume Analysis**: Aggregate volume patterns across timeframes
5. **Reduced Computation**: Higher timeframes reduce bar count for faster backtesting

## Next Steps for Strategy Enhancement

With multi-timeframe data available, you can now implement:

1. **Higher Timeframe Trend Filter**
   - Use 1h or 30m to determine overall trend direction
   - Only take trades aligned with higher timeframe trend

2. **Multi-Timeframe Momentum**
   - Calculate momentum indicators on multiple timeframes
   - Require alignment across timeframes for stronger signals

3. **Volume Profile Analysis**
   - Aggregate volume across different timeframes
   - Identify key volume levels and clusters

4. **Adaptive ORB Periods**
   - Use different opening range periods based on volatility regime
   - Measure volatility on higher timeframes

5. **Time-Based Regime Detection**
   - Identify market regimes using higher timeframe patterns
   - Adapt strategy parameters based on regime

## Technical Details

- **Script**: `scripts/create_multi_timeframe_data.py`
- **Resampling Library**: pandas.DataFrame.resample()
- **Frequency Codes**:
  - 5m: '5T' (5 minutes)
  - 15m: '15T' (15 minutes)
  - 30m: '30T' (30 minutes)
  - 1h: '1H' (1 hour)
- **Data Integrity**: All bars are properly aligned to interval boundaries
- **Completeness**: Incomplete bars at the end of the dataset are dropped

## Data Quality

- ✅ All timeframes span the same date range (2020-10-06 to 2025-10-05)
- ✅ Proper OHLCV aggregation verified
- ✅ Timestamps are UTC and properly aligned to interval boundaries
- ✅ No gaps or missing data
- ✅ Volume properly summed across periods

---

*Generated: October 8, 2025*

