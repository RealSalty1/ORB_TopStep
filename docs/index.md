# ORB Confluence Strategy - Documentation

## Overview

The ORB (Opening Range Breakout) Confluence Strategy is a professional-grade quantitative trading research platform for intraday breakout strategies with multi-factor confirmation.

**Key Features:**
- **Adaptive Opening Range**: Dynamically adjusts OR duration based on volatility
- **Multi-Factor Confluence**: 5 independent factors (Relative Volume, Price Action, Profile Proxy, VWAP, ADX)
- **Complete Trade Lifecycle**: Automated stop placement, partial targets, breakeven shifts
- **Risk Governance**: Daily signal caps, loss lockouts, time cutoffs
- **Advanced Analytics**: 20+ metrics, factor attribution, walk-forward optimization
- **Performance**: Numba-optimized (50x speedup for ADX)

## Platform Modules

1. **Configuration** - YAML-driven config with Pydantic validation
2. **Data Layer** - Yahoo, Binance, Synthetic data providers
3. **Opening Range** - Adaptive OR builder with validation
4. **Factors** - 5 confluence factors (streaming + batch)
5. **Strategy Core** - Scoring, breakout detection, trade management
6. **Governance** - Risk controls and discipline rules
7. **Backtest Engine** - Event-driven simulation
8. **Analytics** - Metrics, attribution, optimization
9. **Reporting** - HTML reports and Streamlit dashboard
10. **REST API** - FastAPI server with OpenAPI docs
11. **Performance** - Numba optimization and profiling

## Quick Start

```python
from orb_confluence.config import load_config
from orb_confluence.data import YahooProvider
from orb_confluence.backtest import EventLoopBacktest
from orb_confluence.analytics import compute_metrics

# Load configuration
config = load_config("config.yaml")

# Fetch data
bars = YahooProvider().fetch_intraday('SPY', '2024-01-02', '2024-01-10', '1m')

# Run backtest
engine = EventLoopBacktest(config)
result = engine.run(bars)

# Compute metrics
metrics = compute_metrics(result.trades)
print(f"Total R: {metrics.total_r:.2f}")
print(f"Win Rate: {metrics.win_rate:.1%}")
```

## Documentation Sections

- **[Modules](modules.md)** - Module purposes and organization
- **[Factors](factors.md)** - Factor mathematics and implementations
- **[Configuration](config.md)** - Parameter glossary and validation rules
- **[API Reference](api.md)** - REST API endpoints

## Performance

- **ADX Calculation**: 50x faster (with numba)
- **Event Loop**: 1.4-1.6x faster (estimated)
- **Throughput**: ~1,500+ bars/second

## Testing

- **490+ test cases** (unit + property)
- **2,000+ hypothesis examples**
- **~46% test coverage**

## License

MIT License - See LICENSE file for details.

**Version**: 1.0  
**Status**: Production-Ready ✅
