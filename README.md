# ORB 2.0 Trading Strategy

A sophisticated Opening Range Breakout (ORB) trading strategy designed for ES futures trading, built for TopStep evaluation.

## 🎯 Overview

This is a multi-playbook, state-aware, probability-gated framework for futures trading that uses:
- **Dual OR System**: Micro (5-7m) and Primary (10-20m adaptive) opening ranges
- **Auction State Classification**: Real-time market structure analysis
- **Context Exclusion Matrix**: Filters low-expectancy trading contexts
- **Two-Phase Stop Management**: Dynamic stop loss with salvage abort logic
- **Probability Gating**: ML-based extension probability for signal filtering
- **Multiple Playbooks**: Classic ORB, Failure Fade, Pullback Continuation, and more

## 📊 Performance (Baseline YTD 2025)

- **Total Trades**: 6,050
- **Win Rate**: 3.44%
- **Total Return**: +21.62R
- **Profit Factor**: 1.21
- **Win/Loss Ratio**: 34:1
- **Max Drawdown**: -10.04R

*Currently in optimization phase - see OPTIMIZATION_PLAN.md for details*

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/RealSalty1/ORB_TopStep.git
cd ORB_TopStep

# Install dependencies
pip install -r requirements.txt
```

### Running a Backtest

```bash
# Run on synthetic data (quick test)
python run_orb2_backtest.py --symbol ES --start 2025-01-01 --end 2025-10-08 --synthetic

# Run on real Databento data
python run_orb2_backtest.py --symbol ES --start 2025-01-01 --end 2025-10-08 --databento --databento-dir data_cache/databento_1m
```

### Launch Dashboard

```bash
# View results in interactive Streamlit dashboard
streamlit run orb_confluence/viz/streamlit_app.py
```

## 📁 Project Structure

```
ORB(15m)/
├── orb_confluence/          # Core strategy package
│   ├── features/            # Feature engineering (OR, auction metrics)
│   ├── states/              # Auction state & context exclusion
│   ├── risk/                # Stop management & salvage logic
│   ├── playbooks/           # Trading playbook implementations
│   ├── models/              # Probability models & calibration
│   ├── signals/             # Signal generation & probability gating
│   ├── backtest/            # Event-driven backtest engine
│   ├── analytics/           # Performance metrics & analysis
│   ├── data/                # Data loaders (Databento, Yahoo)
│   └── viz/                 # Streamlit visualization
├── run_orb2_backtest.py     # Main backtest runner
├── 10_07_implementation.md  # Full specification document
├── OPTIMIZATION_PLAN.md     # Current optimization roadmap
└── README.md                # This file
```

## 🛠️ Key Components

### Opening Range System
- **Micro OR**: 5-7 minute early signal detection
- **Primary OR**: 10-20 minute adaptive range (volatility-based)
- **Buffers**: Dynamic based on auction state

### Auction State Classification
- INITIATIVE: Strong directional moves
- BALANCED: Two-way auction
- COMPRESSION: Range contraction
- GAP_REV: Gap reversion
- INVENTORY_FIX: End-of-day positioning
- MIXED: Unclear state

### Risk Management
- **Two-Phase Stops**: Statistical → Structural → Runner
- **Salvage Abort**: Early exit on MFE retracement
- **Trailing Modes**: Volatility, pivot, hybrid approaches
- **Partial Exits**: Lock in gains at intermediate targets

### Playbooks
1. **PB1 - Classic ORB Refined**: Enhanced breakout logic with auction awareness
2. **PB2 - Failure Fade**: Counter-trend entries on failed breakouts
3. **PB3 - Pullback Continuation**: Breakout retest entries
4. **PB4-6**: Compression, Gap Reversion, Spread Alignment (planned)

## 📈 Current Optimization Status

**Phase 1 (In Progress):**
- [ ] Widen stops to 1.3x (reduce 96% stop-out rate)
- [ ] Add breakeven stop at +0.3R MFE
- [ ] Implement 50% partial exit at +0.5R
- [ ] Add time-of-day filters

**Phase 2 (Planned):**
- [ ] Strengthen entry filters (volume, OR width)
- [ ] Fix context exclusion matrix
- [ ] Reduce trade frequency by 30-40%

**Phase 3 (Planned):**
- [ ] Activate PB2 & PB3 playbooks
- [ ] Add spread alignment logic
- [ ] Smooth equity curve

See [OPTIMIZATION_PLAN.md](OPTIMIZATION_PLAN.md) for full details.

## 📊 Streamlit Dashboard Features

- **Portfolio Performance**: Real-time equity curve with drawdowns
- **Trade Statistics**: Win rate, expectancy, profit factor
- **MFE/MAE Analysis**: Excursion scatter plots
- **Time Analysis**: Performance by hour, day, month
- **Salvage Analysis**: Impact of early exit logic
- **Monthly Heatmap**: Calendar-based returns visualization

## 🔬 Testing & Validation

```bash
# Run unit tests
pytest tests/

# Run specific test suite
pytest tests/test_features.py
pytest tests/test_risk.py
pytest tests/test_playbooks.py
```

## 📚 Documentation

- **[Implementation Spec](10_07_implementation.md)**: Full technical specification
- **[Quick Start Guide](QUICKSTART_ORB_2.0.md)**: Getting started guide
- **[Optimization Plan](OPTIMIZATION_PLAN.md)**: Current optimization roadmap
- **[Implementation Status](ORB_2.0_COMPLETE.md)**: Sprint completion summary

## 🤝 Contributing

This is a private trading system for TopStep evaluation. No contributions accepted at this time.

## 📝 License

Private - All Rights Reserved

## 📧 Contact

For questions or support, contact: [Your Email/Discord]

---

**Status**: Active Development - Phase 1 Optimization  
**Last Updated**: October 8, 2025  
**Version**: 2.0.0
