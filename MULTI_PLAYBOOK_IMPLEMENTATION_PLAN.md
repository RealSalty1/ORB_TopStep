# Multi-Playbook Strategy Implementation Plan

**Based on:** 10_08_project_review.md by Dr. Alexander Hoffman  
**Date:** October 8, 2025  
**Objective:** Transform from single-strategy ORB to institutional-grade multi-regime playbook system

---

## Phase 0: Architecture & Foundation (Days 1-3)

### What We're Keeping ✅
- **Backtest engine**: `orb_confluence/backtest/orb_2_engine.py` (proven, stable)
- **Data infrastructure**: `DatabentoLoader`, multi-timeframe data
- **Analytics**: Trade metrics, reporting, visualization
- **Streamlit dashboard**: UI framework
- **Risk management base**: Position sizing, stop logic foundation

### What We're Building 🏗️

#### Core New Modules
1. **`orb_confluence/features/advanced_features.py`** - 8 institutional features
2. **`orb_confluence/strategy/regime_classifier.py`** - GMM+PCA regime detection
3. **`orb_confluence/strategy/playbook_base.py`** - Base playbook architecture
4. **`orb_confluence/strategy/playbooks/`** - Individual playbook implementations
5. **`orb_confluence/risk/three_phase_stops.py`** - Advanced stop management
6. **`orb_confluence/risk/salvage_system.py`** - Intelligent exit mechanics
7. **`orb_confluence/strategy/signal_arbitrator.py`** - Cross-signal optimization
8. **`orb_confluence/strategy/portfolio_manager.py`** - Multi-instrument position management

---

## Phase 1: Feature Engineering & Regime Classification (Days 1-3)

### 1.1 Advanced Feature Engineering

Create `orb_confluence/features/advanced_features.py`:

**8 Core Features (from review):**

```python
class AdvancedFeatures:
    """Institutional-grade feature engineering for regime detection."""
    
    def volatility_term_structure(self, bars_1m, bars_daily):
        """ATR(14,1m) / ATR(20,daily) - Cross-timeframe energy transfer"""
        
    def overnight_auction_imbalance(self, overnight_bars):
        """abs(ON_POC - ON_VWAP) / ON_Range - Overnight inventory asymmetry"""
        
    def rotation_entropy(self, bars):
        """-Σpᵢlog(pᵢ) where pᵢ = rotation_bar / total_bars - Path complexity"""
        
    def relative_volume_intensity(self, bars, historical_bars):
        """(Vol_first_hour / 20d_avg_first_hour)^2 - 1 - Participation conviction"""
        
    def directional_commitment(self, bars):
        """|Σ(close-open)| / Σ|close-open| - Initiative vs responsive"""
        
    def microstructure_pressure(self, trades_1s):
        """(Bid_vol - Ask_vol) / Total_vol - Order flow imbalance"""
        
    def intraday_yield_curve(self, bars):
        """Σ(high-low) / range_first_hour - Path efficiency"""
        
    def composite_liquidity_score(self, bars_1s):
        """f(spread, volume, trade_size_dist) - Market depth quality"""
```

**Test Suite:**
- Unit tests for each feature
- Validation against known market regimes
- Performance profiling (<10ms per feature calculation)

### 1.2 Regime Classifier

Create `orb_confluence/strategy/regime_classifier.py`:

**Implementation:**
- GaussianMixture with 4 components (TREND, RANGE, VOLATILE, TRANSITIONAL)
- PCA preprocessing (retain 85% variance)
- BIC model selection
- Confusion matrix validation (>80% concordance)

**Training Data Requirements:**
- 2-3 years of ES data minimum
- Expert-labeled regime samples (at least 200 days)
- Cross-validation with silhouette scoring

**Output:**
- Discrete regime label
- Probability distribution across regimes
- Regime strength/clarity score

---

## Phase 2: Playbook Architecture (Days 4-6)

### 2.1 Base Playbook Class

Create `orb_confluence/strategy/playbook_base.py`:

```python
class Playbook(ABC):
    """Base class for all trading playbooks."""
    
    @abstractmethod
    def check_entry(self, market_data, regime, features) -> Optional[Signal]:
        """Check if entry conditions are met."""
        
    @abstractmethod
    def get_initial_stop(self, entry_price, direction) -> float:
        """Calculate initial stop loss."""
        
    @abstractmethod
    def get_profit_targets(self, entry_price, direction) -> List[ProfitTarget]:
        """Calculate profit target levels."""
        
    @abstractmethod
    def update_stops(self, position, market_data, mfe) -> float:
        """Update stops based on three-phase logic."""
        
    @abstractmethod
    def check_salvage(self, position, market_data, mfe) -> bool:
        """Check if position should be salvaged."""
        
    @property
    @abstractmethod
    def name(self) -> str:
        """Playbook name."""
        
    @property
    @abstractmethod
    def preferred_regimes(self) -> List[str]:
        """Regimes where this playbook performs best."""
        
    @property
    @abstractmethod
    def expected_win_rate(self) -> float:
        """Historical win rate."""
        
    @property
    @abstractmethod
    def expected_avg_win(self) -> float:
        """Historical average win in R."""
        
    @property
    @abstractmethod
    def expected_avg_loss(self) -> float:
        """Historical average loss in R."""
```

### 2.2 Signal Data Structure

```python
@dataclass
class Signal:
    """Trading signal from a playbook."""
    playbook_name: str
    direction: str  # 'LONG' or 'SHORT'
    entry_price: float
    initial_stop: float
    profit_targets: List[ProfitTarget]
    strength: float  # 0-1 signal strength
    regime_alignment: float  # 0-1 regime fit
    confidence: float  # 0-1 overall confidence
    metadata: Dict[str, Any]  # Additional context
```

---

## Phase 3: Core Playbooks (Days 7-12)

### 3.1 Initial Balance Fade (Mean Reversion)

Create `orb_confluence/strategy/playbooks/ib_fade.py`:

**Key Components:**
- Auction Efficiency Ratio (AER)
- Acceptance velocity detection (15s/30s micro-bars)
- Distribution tail analysis (>92nd percentile)
- Seasonality matrix (day-of-week adjustments)

**Entry Rules:**
- IB established (first 60 minutes)
- Extension beyond IB by X ticks (dynamic threshold)
- AER < 0.65 (poor conviction)
- Acceptance velocity increasing
- Regime: RANGE or VOLATILE

**Exit Rules:**
- Target: IB midpoint or opposite IB extreme
- Stop: 1.2x extension beyond recent high/low
- Three-phase trailing once in profit

### 3.2 VWAP Magnet (Mean Reversion)

Create `orb_confluence/strategy/playbooks/vwap_magnet.py`:

**Key Components:**
- Dynamic VWAP bands (volatility-adjusted)
- VWAP rejection velocity
- Multi-timeframe VWAP (intraday, 3d, 5d)
- Compression zone identification

**Entry Rules:**
- Price extends beyond adaptive VWAP band
- High rejection velocity away from VWAP
- Volume confirms exhaustion
- Regime: RANGE or TRANSITIONAL

**Exit Rules:**
- Target: VWAP or opposite band
- Stop: Fixed R-multiple (0.8-1.0R)
- Time-based exit if stalling (>45 min)

### 3.3 Momentum Continuation (Trend Following)

Create `orb_confluence/strategy/playbooks/momentum_continuation.py`:

**Key Components:**
- Impulse Quality Function (IQF)
- Microstructure continuation signals (order flow)
- Multi-timeframe alignment (5m, 15m, 60m)
- Asymmetric exit framework

**Entry Rules:**
- Strong impulse (IQF > 1.8)
- Pullback to structure (50-61.8% Fib or moving average)
- Order flow confirms continuation
- Regime: TREND

**Exit Rules:**
- Target: Extension beyond impulse high/low
- Stop: Below pullback low (tight)
- Dynamic trailing based on realized vol
- Partial exits at 1.5R, 2.5R, runners

### 3.4 Opening Drive Reversal

Create `orb_confluence/strategy/playbooks/opening_drive_reversal.py`:

**Key Components:**
- Tape speed analysis (trade arrival rate)
- Volume delta distribution (buy vs sell aggression)
- Block trade filtering
- Overnight gap treatment

**Entry Rules:**
- First 5-15 minutes post-open
- Aggressive move but declining tape speed
- Volume delta showing exhaustion
- No block trades (institutional conviction)
- Regime: Any (but strength varies)

**Exit Rules:**
- Target: Opening price or prior close
- Stop: Recent high/low + buffer
- Quick exit if drive resumes

---

## Phase 4: Advanced Risk Management (Days 13-15)

### 4.1 Three-Phase Stop System

Create `orb_confluence/risk/three_phase_stops.py`:

**Phase 1 (0-0.5R MFE): Statistical Stop**
- MAE distribution 75-80th percentile
- Tight, capital preservation focused

**Phase 2 (0.5-1.25R MFE): Structural + Volatility**
- Structural pivot + 0.5σ buffer
- Breathing room while protecting profit

**Phase 3 (>1.25R MFE): Aggressive Trailing**
- Parabolic SAR or time-decay trailing
- Maximize profit capture

### 4.2 Salvage System

Create `orb_confluence/risk/salvage_system.py`:

**Salvage Score Formula:**
```
Salvage_Score = 0.4 × (Retrace_Pct/0.7) + 
                0.3 × (Bars_Since_MFE/Threshold) + 
                0.3 × (Velocity_Decay/Threshold)
```

**Features:**
- Conditional thresholds by regime
- Efficacy tracking (opportunity cost analysis)
- Adaptive learning (optimize thresholds over time)

---

## Phase 5: Signal Orchestration (Days 16-18)

### 5.1 Signal Arbitrator

Create `orb_confluence/strategy/signal_arbitrator.py`:

**When Multiple Signals Conflict:**

```
Signal_Priority = Σ wᵢ × Fᵢ

Where:
- F₁ = Regime alignment score (0-1)
- F₂ = Historical expectancy in current hour
- F₃ = Signal strength percentile
- F₄ = Capital efficiency (R / expected bars)
- F₅ = Correlation-adjusted portfolio contribution
```

**Features:**
- Dynamic weight optimization (Bayesian bandit)
- Cross-entropy minimization (avoid redundant exposure)
- Real-time signal ranking

### 5.2 Portfolio Manager

Create `orb_confluence/strategy/portfolio_manager.py`:

**Capabilities:**
- Volatility targeting (normalize by realized vol)
- Correlation-weighted exposure (ES+NQ adjustment)
- Regime-conditional position limits
- Internal beta-neutralization

---

## Phase 6: Integration & Testing (Days 19-25)

### 6.1 Strategy Orchestrator

Create `orb_confluence/strategy/multi_playbook_strategy.py`:

**Main Strategy Class:**
```python
class MultiPlaybookStrategy:
    """Orchestrates multiple playbooks with regime awareness."""
    
    def __init__(self):
        self.regime_classifier = RegimeClassifier()
        self.feature_engine = AdvancedFeatures()
        self.playbooks = [
            IBFadePlaybook(),
            VWAPMagnetPlaybook(),
            MomentumContinuationPlaybook(),
            OpeningDriveReversalPlaybook()
        ]
        self.signal_arbitrator = SignalArbitrator()
        self.portfolio_manager = PortfolioManager()
        self.risk_manager = ThreePhaseRiskManager()
        
    def on_bar(self, bar_data):
        """Process new bar and generate signals."""
        # 1. Calculate features
        # 2. Detect regime
        # 3. Check each playbook for signals
        # 4. Arbitrate signals
        # 5. Size positions
        # 6. Manage existing positions
        # 7. Update stops (three-phase)
        # 8. Check salvage conditions
```

### 6.2 Backtest Integration

**Modify `orb_confluence/backtest/orb_2_engine.py`:**
- Keep event loop structure (proven, reliable)
- Replace `ORB2Strategy` with `MultiPlaybookStrategy`
- Add regime tracking to results
- Add per-playbook performance metrics

### 6.3 Testing Suite

**Create comprehensive tests:**
- Unit tests for each feature (100% coverage)
- Playbook entry/exit logic tests
- Regime classifier validation
- End-to-end backtest tests
- Performance benchmarks

---

## Phase 7: Optimization & Validation (Days 26-30)

### 7.1 Parameter Optimization

**For Each Playbook:**
- Walk-forward optimization (6-month train, 1-month test)
- Sensitivity analysis (parameter stability)
- Regime-specific parameter sets

### 7.2 Statistical Validation

**Metrics to Track:**
- Per-playbook expectancy (target: 0.15-0.25R)
- Win rate by regime
- MAE/MFE distributions
- Time-in-trade distributions
- Salvage efficacy ratios

### 7.3 Stress Testing

**Scenarios:**
- High volatility (VIX >30)
- Low volatility (VIX <12)
- Regime transitions
- Gap events
- News releases (FOMC, CPI, NFP)

---

## Data Requirements

### Minimum Historical Data
- **ES 1-minute bars**: 2020-present (already have ✅)
- **ES 1-second bars**: Sept-Oct 2025 (just added ✅)
- **ES tick data**: Sept-Oct 2025 (just added ✅)

### For Advanced Features
- **Multi-timeframe**: 1s, 1m, 5m, 15m, 30m, 1h (ready ✅)
- **Order flow**: Bid/ask aggressor from tick data (ready ✅)
- **Volume profile**: Can derive from 1s bars ✅

### For Regime Training
- **Expert labels**: Need to manually label 200+ days by regime
- **Market events**: Economic calendar data
- **Volatility data**: VIX or equivalent

---

## Success Metrics

### Phase 1-3 (Foundation)
- ✅ All features calculate correctly (<10ms each)
- ✅ Regime classifier >80% concordance with expert labels
- ✅ All playbooks pass unit tests
- ✅ Signal generation <150ms SLA

### Phase 4-6 (Integration)
- ✅ Backtest runs successfully on 2024-2025 data
- ✅ No position management errors
- ✅ Risk system prevents runaway losses
- ✅ All trades logged with full metadata

### Phase 7 (Validation)
- ✅ Overall expectancy: 0.15-0.25R per trade
- ✅ Win rate: 47-52% (blended)
- ✅ Sharpe ratio: >1.5 (post-costs)
- ✅ Monthly return: 4.5-7.5% target
- ✅ Max drawdown: <12%
- ✅ Each playbook profitable independently

---

## Implementation Order (Recommended)

### Week 1: Foundation
1. ✅ Advanced features module
2. ✅ Feature calculation tests
3. ✅ Regime classifier (GMM+PCA)
4. ✅ Base playbook architecture

### Week 2: Core Playbooks
5. ✅ IB Fade playbook (mean reversion)
6. ✅ VWAP Magnet playbook (mean reversion)
7. ✅ Playbook unit tests
8. ✅ Basic signal generation tests

### Week 3: Advanced Components
9. ✅ Three-phase stop system
10. ✅ Salvage mechanics
11. ✅ Momentum Continuation playbook
12. ✅ Opening Drive Reversal playbook

### Week 4: Orchestration
13. ✅ Signal arbitrator
14. ✅ Portfolio manager
15. ✅ Multi-playbook strategy class
16. ✅ Backtest engine integration

### Week 5: Validation
17. ✅ Full system testing
18. ✅ Parameter optimization
19. ✅ Walk-forward validation
20. ✅ Documentation & final review

---

## Risk Mitigation

### Technical Risks
- **Complex system**: Mitigate with modular design, comprehensive tests
- **Performance**: Mitigate with profiling, caching, vectorization
- **Integration errors**: Mitigate with staging environment, gradual rollout

### Strategy Risks
- **Overfitting**: Mitigate with walk-forward validation, parameter haircuts
- **Regime drift**: Mitigate with CUSUM monitoring, regular retraining
- **Correlation changes**: Mitigate with dynamic correlation tracking

### Operational Risks
- **Data quality**: Mitigate with validation checks, alerting
- **Execution delays**: Mitigate with latency monitoring, contingency plans
- **Parameter drift**: Mitigate with version control, A/B testing

---

## Deliverables

### Code
- [ ] 12+ new Python modules (clean, documented, tested)
- [ ] Updated backtest engine with multi-playbook support
- [ ] Configuration system for playbook parameters
- [ ] Comprehensive test suite (>80% coverage)

### Documentation
- [ ] Architecture overview
- [ ] Per-playbook specification documents
- [ ] Feature engineering reference
- [ ] Regime classification guide
- [ ] Parameter optimization guide
- [ ] User manual for running backtests

### Validation
- [ ] Full 2024-2025 backtest results
- [ ] Per-playbook performance analysis
- [ ] Regime performance breakdown
- [ ] Statistical validation report
- [ ] Stress test results

---

## Next Steps

**Immediate (Today):**
1. Create `orb_confluence/features/advanced_features.py` skeleton
2. Implement first 3 features (volatility_term_structure, rotation_entropy, relative_volume_intensity)
3. Write unit tests for these features
4. Validate on historical data

**Tomorrow:**
1. Complete remaining 5 features
2. Build RegimeClassifier with GMM+PCA
3. Create expert regime labels for 50 days (training set)
4. Train and validate classifier

**This Week:**
1. Finish foundation (features + regime classifier)
2. Build playbook base architecture
3. Implement IB Fade playbook
4. Initial tests with existing backtest engine

---

*This is a major evolution. We're building institutional infrastructure that will serve you for years. Let's be methodical, thorough, and test everything.*

**Ready to start?** Reply with:
- `BEGIN_PHASE_1` - Start with features & regime classifier
- `REVIEW_ARCHITECTURE` - Discuss architecture decisions first
- `MODIFY_PLAN` - Suggest changes to the plan

