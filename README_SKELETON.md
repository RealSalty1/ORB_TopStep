# ORB Confluence Strategy (Free Track)

Initial project skeleton for the Opening Range Breakout strategy with multi-factor confluence.

## Project Status

🚧 **SKELETON PHASE** - Core structure in place, implementations pending.

This is a scaffolded project with:
- ✅ Complete directory structure
- ✅ Configuration system with pydantic validation
- ✅ Data provider interfaces (Yahoo, Binance, Synthetic)
- ✅ Feature calculation stubs (OR, ATR, factors)
- ✅ Strategy component stubs (scoring, breakout, risk)
- ✅ Backtest framework outline
- ✅ Analytics and visualization placeholders
- ✅ Test suite with fixtures
- ⏳ **Full implementations pending** (marked with TODO comments)

## Quick Start

```bash
# Install dependencies
poetry install

# Run tests (many will be xfail - expected)
poetry run pytest

# Check configuration
poetry run python -c "from orb_confluence.config import get_default_config, load_config; print(load_config(get_default_config()))"
```

## Directory Structure

```
orb_confluence/
├── config/              # Configuration schemas and YAML
├── data/               # Data providers and QC
│   └── sources/        # Yahoo, Binance, Synthetic
├── features/           # OR builder, indicators, factors
├── strategy/           # Scoring, breakout, risk, trade state
├── backtest/           # Event loop, vectorized, fills
├── analytics/          # Metrics, attribution, reporting
├── viz/                # Plotting and Streamlit dashboard
├── tests/              # Test suite (pytest)
└── utils/              # Timezones, logging, IDs, hashing
```

## Next Steps

1. **Implement Core Features**:
   - Complete `features/opening_range.py` (adaptive OR)
   - Finish `features/adx.py` (ADX calculation)
   - Fill in factor calculation logic

2. **Build Strategy Layer**:
   - Complete `strategy/scoring.py` (weighted confluence)
   - Implement `strategy/breakout.py` (second chance logic)
   - Finish `strategy/trade_state.py` (lifecycle management)

3. **Develop Backtest Engine**:
   - Implement `backtest/event_loop.py` (full event-driven loop)
   - Complete `backtest/fills.py` (conservative fill model)

4. **Add Analytics**:
   - Build `analytics/attribution.py` (factor performance)
   - Implement `analytics/perturbation.py` and `analytics/walk_forward.py`

5. **Testing**:
   - Remove `xfail` markers as implementations complete
   - Add property-based tests with hypothesis
   - Add integration tests

## Configuration

See `orb_confluence/config/defaults.yaml` for baseline parameters.

Key sections:
- `instruments`: Symbol mappings (proxy mode for free data)
- `orb`: Opening range parameters
- `factors`: Enable/disable factors and their settings
- `scoring`: Confluence weights and thresholds
- `trade`: Stop modes, partials, breakeven
- `governance`: Daily caps, lockouts, cutoffs

## Design Principles

- **Modularity**: Each component is independent
- **Testability**: Pure functions, dependency injection
- **Extensibility**: Easy to add factors/data sources
- **Performance**: Numba JIT where needed
- **Type Safety**: Full type hints throughout
- **Logging**: Structured logging with loguru

## License

MIT License - See LICENSE file.

## Notes

This skeleton follows the free track specification:
- Uses only free data sources (Yahoo, Binance, synthetic)
- No paid dependencies
- Designed for rapid validation before production investment

All TODO comments indicate areas needing implementation.
