# ORB 2.0 Implementation Details  
Transforming a Single ORB Breakout System into a Multi-Playbook Opening Auction & Early Session Exploitation Framework

Version: 1.0  
Author: Senior Quant Engineering Spec  
Audience: Quant Devs, Strategy Researchers, Platform Engineers  
Status: Approved for Build (Pending Module Prioritization)  

---

## 0. Objective Summary

This document specifies the **full implementation blueprint** to upgrade the current (near‑breakeven) ORB strategy into a **multi‑playbook, state‑aware, probability‑gated framework** focused on ES first, modular for NQ, CL, GC, 6E later.  
Core goals:

| Goal | Description | KPI |
|------|-------------|-----|
| Edge Preservation | Preserve existing 58% directional correctness while improving payoff | Expectancy from -0.22R → +0.10–0.15R |
| Loss Compression | Reduce avg full loss magnitude using path-dependent stop logic | Avg loser -1.27R → ≤ -0.90R |
| Payoff Convexity | Capture more tail outcomes via state-specific exits & probability gating | Avg winner +0.50R → +0.65–0.75R |
| Context Filtering | Prune structurally low-expectancy sessions | Bottom decile context removal |
| Diversification | Introduce orthogonal opening tactics (failure fade, pullback continuation) | ≥ 3 positive playbooks |
| Evaluation Readiness | Provide regime-conditioned analytics | Conditional expectancy grid (State × Regime) |
| Prop Constraints | Align risk pacing (Topstep style) | Max daily risk tolerance adherence ≥ 99% sim days |

---

## 1. Architecture Overview

### 1.1 Layered System

| Layer | Module Group | Purpose |
|-------|--------------|---------|
| Data Acquisition | `data/` | Load & cache minute futures, build continuous front contracts, roll adjustments |
| Feature Fabrication | `features/` | OR layers, volatility, auction state, volume normalization, relative strength |
| State Classification | `states/` | Auction state, regime, context exclusion |
| Playbook Engine | `playbooks/` | Encapsulates each tactic (ORB, Failure Fade, Pullback Continuation, Compression Expansion, Gap Reversion, Spread Alignment) |
| Signal Vetting | `signals/` | Probability gating, correlation & governance filters |
| Risk & Execution | `risk/`, `trade/` | Two-phase stop, salvage abort, exit archetype, trailing frameworks |
| Probability Modeling | `models/` | Extension probability (logistic or GBDT), calibration |
| Backtest Runtime | `engine/` | Event-driven synchronous loop, multi-instrument scheduling |
| Analytics | `analytics/` | MFE/MAE tables, context heatmap, playbook attribution, drift detection |
| Monitoring & Drift | `monitor/` | Rolling expectancy z-scores, salvage performance validation |
| Visualization | `viz/` | Streamlit v2 + optional React API skeleton |
| Persistence | `store/` | Parquet (bars, factor matrix, trades), model snapshots, config hash lineage |

### 1.2 Design Principles
- **Playbook Abstraction**: Each tactic generates candidate signals with metadata (confidence, required exit type).
- **State Before Signal**: No signal generation until auction state resolved.
- **Probability as Gate, Not Oracle**: p(extension) curves guide exit choice, not raw “enter/skip” unless below floor.
- **Path-Dependent Risk**: Stop evolution driven by realized path (phase thresholds & salvage triggers).
- **Composable Filters**: Regime, context exclusion, correlation, daily risk envelope—all composable reducers.

---

## 2. Data & Preprocessing

### 2.1 Data Sources
- Raw 1‑minute OHLCV (Databento or equivalent)
- Continuous contract building with **no calendar spread artifacts**:
  - Filter `contract` strings containing `-`
  - Roll logic: front contract until (vol_front < 0.85 * vol_next OR days_to_expiry ≤ threshold)
  - Optional backward-adjust via difference method (for visual continuity only)
- Overnight session included for:
  - Overnight range
  - Inventory bias
  - Gap classification
- Pre-market filter: remove holiday-shortened sessions (`session_minutes < threshold`)

### 2.2 Session Partitions
| Session Block | Use |
|---------------|-----|
| Overnight (ON): Previous settlement → 08:29:59 CT | Inventory bias, overnight range |
| Auction Window: 1st N min (micro + primary OR) | State inference |
| Expansion Zone: OR end → 120 mins | Primary breakout & follow-through |
| Mid Transition: 120–180 mins | Reduced weighting (fewer primary signals) |
| Off-Limits | After daily loss lock / trailing drawdown breach |

### 2.3 Feature Pipelines

#### Core Feature Table Schema
| Column | Type | Description |
|--------|------|-------------|
| ts | datetime | Bar open |
| instrument | str | ES, NQ, etc. |
| o/h/l/c/v | float | OHLCV |
| atr_14 / atr_60 | float | ATR references |
| ret_1m | float | Log return |
| or_micro_high/low | float | Micro OR (5–7m) |
| or_primary_high/low | float | Adaptive OR (10–20m) |
| or_width_norm | float | Width / ATR(14) |
| drive_energy | float | Sum(|body|)/OR width weighting |
| rotations | int | Count direction alternations |
| vol_z | float | Volume deviation z-score vs time-of-day median |
| gap_type | enum | FULL_UP, FULL_DOWN, PARTIAL, INSIDE |
| overnight_range_pct | float | ON range / ADR(20) |
| vwap | float | Session VWAP |
| vwap_dev_norm | float | (Price - VWAP)/ATR |
| es_nq_spread | float | ES return - NQ return (for indices) |
| auction_state | enum | INITIATIVE, BALANCED, COMPRESSION, GAP_REV, INVENTORY_FIX, MIXED |
| regime_vol | enum | LOW, NORMAL, EXPANSION |
| context_excluded | bool | If removed by exclusion matrix |
| p_extension | float | Model predicted P(≥ target before stop) |
| spread_signal | float | Spread bias indicator |
| ... | ... | Extendable |

All features persisted to Parquet for offline auditing.

---

## 3. Auction State Classification

### 3.1 Rule-Based v1 (Bootstrap Before ML)
```
if drive_energy >= D1 and rotations <= R1 and vol_z >= Z1:
    state = INITIATIVE
elif or_width_norm <= W_low and entropy(price_directions) <= E_low:
    state = COMPRESSION
elif gap_abs >= G_big and failure_to_extend:
    state = GAP_REV
elif rotations >= R_bal and vol_z between Zl & Zh:
    state = BALANCED
elif overnight_inventory_extreme and open reversion:
    state = INVENTORY_FIX
else:
    state = MIXED
```
Parameters D1, R1, Z1, etc. tuned via grid search on historical classification stability & conditional expectancy separation.

### 3.2 ML Upgrade (Phase 2)
- Inputs: (drive_energy, width_norm, rotations, vol_z, gap_rel, ON range %, open_vs_ON_mid)
- Clustering (k-means 5–6 clusters), label clusters with highest semantic overlap toward above states.

### 3.3 State Confidence
Store posterior-like confidence vector (softmax over cluster distances). Low confidence → reduce size / skip ambiguous states.

---

## 4. Playbooks (Modular Tactics)

Each playbook implements interface:
```python
class Playbook:
    name: str
    def eligibility(state, features) -> bool
    def generate_signals(context) -> list[CandidateSignal]
    def preferred_exit_mode(context) -> ExitModeDescriptor
```

### 4.1 PB1: Classic ORB (Refined)
| Component | Specification |
|-----------|---------------|
| Eligibility | state ∈ {INITIATIVE, COMPRESSION (if width_norm ok)} & not context_excluded |
| Entry Logic | Break +: (body close beyond trigger OR retest + confirm) |
| Buffer | `buffer = base + α*std(ret_1m,last10) + β*rotation_penalty` |
| Exit Mode | Initiative: Minimal partial (20% at 1.2R) + volatility trailing; Compression: no partial until 1.5R or time decay |
| Salvage | If MFE ≥ 0.4R and retrace ≥ 65% and no reclaim in 6 bars → salvage exit |

### 4.2 PB2: OR Failure Fade
| Aspect | Logic |
|--------|-------|
| Trigger | Wick-only break beyond OR followed by close back inside + volume fade |
| Entry | Opposite direction at reclaim of OR mid OR rejection pivot |
| Stop | Just outside failed extreme |
| Target | VWAP or opposite OR quartile; time stop if no progress in X minutes |
| Exit Mode | Single-stage (no runner) |

### 4.3 PB3: Pullback Continuation (Post-Impulse)
| Aspect | Logic |
|--------|-------|
| Trigger | MFE ≥ impulse_threshold_R within ≤ impulse_time bars after open |
| Setup | First orderly bull/bear flag / VWAP retest not closing back inside |
| Entry | Break of flag continuation line |
| Exit | No early partial; trail structural pivots + ATR fallback |
| Abort | If flag length/time ratio > threshold (losing momentum) |

### 4.4 PB4: Compression Expansion
| Aspect | Logic |
|--------|-------|
| Eligibility | or_width_norm in bottom decile & COMPRESSION state |
| Confirmation | Volatility uptick (std 1m returns rising), directional bias (VWAP delta sign) |
| Entry | Break of compression envelope outside ± envelope_width |
| Exit | Trail only; no fixed partial until 2.0R |

### 4.5 PB5: Gap Reversion
| Aspect | Logic |
|--------|-------|
| Gap Classification | FULL gap failing extension (two attempts, both wicks) |
| Entry | Reclaim of open price OR failure at gap extreme + reversal bar |
| Target | VWAP → prior settlement midpoint (2-layer) |
| Stop | Above/below failed extreme |
| Time Governance | If not > 0.5R in 25 minutes, exit |

### 4.6 PB6: Spread Alignment (ES vs NQ)
| Aspect | Logic |
|--------|-------|
| Pre-Condition | Divergent early returns; leader breaks OR; laggard near break |
| Entry | Long leader only if spread normalization expected OR pairs (long strong, short weak) |
| Exit | Spread mean reversion or leader MFE stall slope flattening |
| Risk Model | Spread stop: spread deviation > threshold |

---

## 5. Risk & Trade Management

### 5.1 Two-Phase Stop Algorithm
| Phase | Activation | Stop Basis |
|-------|------------|-----------|
| Phase 1 (Statistical) | Entry → until MFE ≥ phase2_trigger_R (e.g., 0.6R) | 80th percentile MAE of historical winners (per playbook) |
| Phase 2 (Expansion) | Once MFE ≥ trigger | Structural anchor (OR opposite / local pivot / dynamic VWAP zone) |
| Phase 3 (Runner Optional) | If MFE ≥ runner_activation_R & p_extension ≥ threshold | Trail via volatility envelope or structural ladder |

Pseudocode:
```python
if not phase2 and MFE >= phase2_trigger:
    phase2 = True
    stop = max(current_stop, structural_anchor)
elif not phase2:
    if MAE >= phase1_stop_dist: exit("PHASE1_STOP")
```

### 5.2 Salvage Abort
```
if MFE >= salvage_trigger_R
  and retrace_ratio >= salvage_retrace_threshold
  and bars_since_peak >= salvage_confirmation_bars
  and NOT regained_fractional_recovery
    exit("SALVAGE")
```
Config per playbook; track salvage success rate & false positive ratio.

### 5.3 Exit Mode Registry
| Mode | Description |
|------|-------------|
| TRAIL_VOL | Envelope (ATR * k) trailing |
| TRAIL_PIVOT | Update under/over last confirmed swing pivot |
| HYBRID_VOL_PIVOT | Pivot priority; fallback to envelope on volatility expansion |
| SINGLE_TARGET | One fixed objective (reversion playbooks) |
| PARTIAL_THEN_TRAIL | 1 small partial → switch to trail |
| TIME_DECAY_FORCE | Flatten if slope(MFE/time) < slope_min over window |

### 5.4 Probability-Gated Runner
- Use `p_extension ≥ p_thresh`.  
- If below, compress trailing stop earlier & disable runner scaling.
- Calibration every 4 weeks (recalibrate Brier, reliability curve).

### 5.5 Correlation & Exposure Controller
| Rule | Logic |
|------|-------|
| Max Concurrent Risk Units | Sum(risk_R * correlation_weight) ≤ R_budget (e.g., 2.5R) |
| Correlation Weight | ρ_ES,NQ ~ 0.9 → weight NQ as 0.9 risk units |
| Rank Preference | Favor higher state confidence or higher p_extension |

---

## 6. Probability & Modeling Layer

### 6.1 Extension Probability Model (v1)
Target: Binary label = 1 if trade attained ≥ target_R (e.g., 1.8R) before hitting -1R baseline stop.

Features:
- width_norm
- breakout_delay_minutes
- drive_energy
- vol_z
- vwap_dev_norm
- auction_state (one-hot)
- rotations
- impulse_mfe_5bars / atr
- gap_type
- ON range %
- (Optional) es_nq_spread_momentum

Model Options:
- Logistic Regression (transparent baseline)
- Gradient Boosted Trees (LightGBM / XGBoost) for non-linear interactions
- Calibration via isotonic regression

Performance Metrics:
- ROC AUC (target > 0.60 acceptable initial)
- Brier Score
- Reliability plot bucketing (10 buckets)

### 6.2 Drift Detector
- Monitor rolling AUC over trailing 200 trades.
- If AUC < baseline_mean - 2*std → trigger model review flag.

---

## 7. Context Exclusion Matrix

Dimensions:
- OR Width Quartile (Q1–Q4)
- Breakout Delay Bucket (0–10, 10–25, 25–40, >40)
- Volume Quality Tercile (Low, Mid, High)
- Auction State
- Gap Type

Matrix cell metrics:
- Trade Count
- Expectancy
- CI (bootstrap)
- p_extension mean vs global

Prune Rules:
1. If trade count ≥ N_min (e.g., 30) AND expectancy < global_expectancy - threshold (e.g., -0.25R)
2. Or if p_extension mean < p_global - Δp

Caching:
- Recompute weekly.
- Persist snapshot with timestamp & config hash.

---

## 8. Analytics & Reporting Enhancements

| Report Section | Content |
|----------------|---------|
| Playbook Attribution | R contribution, expectancy per playbook |
| Salvage Effect | Pre/post salvage average loss delta |
| Exit Mode Efficiency | Runner capture % vs theoretical MFE tail |
| Context Heatmap | Expectancy grid (state × width × delay) |
| Probability Calibration | Reliability curve, Brier components |
| Regime Profile | Expectancy across vol regime buckets |
| Drift Warnings | Statistical alerts (AUC drop, salvage false positives rising) |
| Capital Efficiency | Average bar-time in trade vs R produced |
| Risk Utilization | Daily risk budget usage histogram |

---

## 9. Testing & Validation Strategy

| Test Type | Module | Method |
|-----------|--------|--------|
| Unit | Feature extractors | Deterministic mock bars |
| Unit | Auction classification | Synthetic state edge cases |
| Property | Stop logic | Ensure no risk inversion (stop < entry for long) |
| Scenario | Playbook PB1 | Simulate initiative vs failure |
| Scenario | Salvage system | Cases: valid salvage vs false salvage (should not exceed threshold rate) |
| Regression | Full backtest | Baseline config hash reproducibility |
| Statistical | Probability model | K-fold OOS; bootstrap CI |
| Performance | Engine throughput | Bars/sec with N instruments |
| Integration | Multi-playbook conflict | Only highest priority signal accepted |
| Risk | Daily cap enforcement | Simulated heavy-loss day |

Automated test harness using `pytest` + `hypothesis` + small synthetic bar generator.

---

## 10. Logging & Observability

| Event | Fields |
|-------|--------|
| SIGNAL_CANDIDATE | playbook, auction_state, features_hash, buffer, p_extension |
| TRADE_OPEN | trade_id, size, entry_type, risk_phase |
| STOP_UPDATE | trade_id, old_stop, new_stop, reason (PHASE2_TRANSITION, TRAIL_PIVOT, VOL_CONTRACTION) |
| SALVAGE_EXIT | trade_id, salvage_trigger_R, retrace%, bars_since_peak |
| RUNNER_ENABLE | trade_id, p_extension, MFE |
| CONTEXT_PRUNE | context_signature, reason |
| PLAYBOOK_SKIP | playbook, reason (CONTEXT_EXCLUDED, RISK_BUDGET_FULL, CORRELATION_LIMIT) |
| DRIFT_ALERT | model_name, metric, threshold_triggered |

Log format: structured JSON; keys include `run_id`, `config_hash`, `instrument`.

---

## 11. Configuration Structure (YAML)

```yaml
core:
  instruments: [ES]
  run_mode: BACKTEST
  random_seed: 42

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
    phase2_trigger_R: 0.6
    salvage:
      trigger_R: 0.4
      retrace_ratio: 0.65
      confirm_bars: 6
  PB2_FAILURE_FADE:
    enabled: true
    wick_ratio_min: 0.55
    reenter_mid: true
  # etc.

risk:
  initial_phase1_stop_pct_mae_winner: 0.80
  max_concurrent_r_units: 2.5
  correlation_matrix:
    ES:
      ES: 1.0
      NQ: 0.9

probability_model:
  target_R: 1.8
  min_samples_retrain: 500
  p_extension_threshold: 0.42

context_exclusion:
  min_trades_cell: 30
  max_bad_decile_pct: 0.10

governance:
  daily_loss_R_limit: -3.0
  max_trades_per_day: 3

reporting:
  output_dir: runs/
  generate_heatmaps: true
```

---

## 12. Implementation Order (Recommended Sprints)

| Sprint | Focus | Deliverables |
|--------|-------|--------------|
| S1 | Feature Foundation & MFE/MAE stats | Feature table builder, MFE/MAE distribution export |
| S2 | Auction State v1 + OR dual layer | Classification module, unit tests |
| S3 | Context Exclusion Matrix | Heatmap engine + pruning logic |
| S4 | Two-Phase Stop + Salvage | Risk module rewrite, salvage tracking |
| S5 | Playbook PB1 Refactor | Refined ORB w/ state integration |
| S6 | Add PB2 + PB3 | Failure fade & pullback continuation |
| S7 | Exit Architecture (Trailing Modes) | Trail registry, parameter tuning script |
| S8 | Probability Model v1 | Logistic pipeline + calibration |
| S9 | Probability Gating + Runner Logic | Integration & performance tests |
| S10 | Portfolio Exposure Controller | Correlation-weighted allocation |
| S11 | Analytics Suite | Reports, dashboards, drift monitor |
| S12 | OOS Backtest & Stability Study | Rolling windows, bootstrap CI |
| S13 | ES Paper Mode Harness | Live simulation engine wrapper |
| S14 | Optional Additional Playbooks | Compression expansion, gap reversion |
| S15 | Refactor & Optimization | Profiling + vectorization (Numba) |

---

## 13. KPIs & Acceptance Criteria

| KPI | Target | Acceptance |
|-----|--------|-----------|
| Expectancy (ES OOS 12M) | ≥ +0.08R | After S12 |
| Avg Loser | ≤ -0.95R | After S4 |
| Avg Winner | ≥ +0.65R | After S7 |
| Win Rate | 52–58% (healthy range) | No degradation below 50% |
| Salvage Recovery | ≥ 12% of full-loss candidates reduced | After S4 |
| Model Calibration (Brier) | ≤ 0.20 | After S8 |
| Drift False Positives | < 5% of alerts | After S11 |
| Exclusion Matrix Improvement | +0.04R vs no exclusion | After S3 |
| Playbook Diversification | ≥ 3 positive expectancy playbooks | After S9 |
| Risk Compliance | 0 unauthorized over-R exposures | Continuous |

---

## 14. Risk Analysis & Mitigations

| Risk | Description | Mitigation |
|------|-------------|------------|
| Overfitting Playbook Conditions | Post-hoc curve fit of rules | OOS splits, forward validation windows |
| Model Drift | p_extension loses reliability | Rolling AUC + calibration refresh |
| Execution Complexity | Increased path logic introduces bugs | Extensive unit + scenario tests before bundling |
| Latency (future live) | Multi-instrument scanning overhead | Pre-compute features in batch / asynchronous stream |
| Data Anomalies | Rollover gaps, missing bars | Pre-flight day integrity validator |
| Regime Shift | Vol structure changes | Regime adaptation gating + dynamic threshold scaling |

---

## 15. Future Enhancements (Phase 2+)

| Idea | Benefit |
|------|---------|
| Order Flow Micro-Structures (CVD, imbalance) | Better initiative detection |
| Real Volume Profile Integration | Replace proxy w/ actual distributions |
| Reinforcement Learning Exit Policy (only after stable baseline) | Non-linear payoff exploitation |
| Multi-Day Compression Pattern Detector | Higher timeframe breakout synergy |
| Macro Event Awareness (FOMC/NFP gating) | Risk normalization |
| Synthetic Data Stress Generator (adversarial volatility days) | Robustness Hardening |
| Live Broker Adapter (Rithmic / CQG) | Paper trading pipeline |

---

## 16. Repository Structure (Additions)

```
orb_confluence/
  data/
  features/
    or_layers.py
    auction_metrics.py
    volume_curve.py
    rotations.py
  states/
    auction_state.py
    regime_detector.py
    context_exclusion.py
  playbooks/
    pb_orb.py
    pb_failure_fade.py
    pb_pullback_continuation.py
    pb_compression_expansion.py
  signals/
    candidate.py
    probability_gate.py
  risk/
    two_phase_stop.py
    salvage.py
    trailing_modes.py
  models/
    extension_model.py
    calibration.py
    drift_monitor.py
  analytics/
    mfe_mae.py
    heatmaps.py
    playbook_attribution.py
    probability_calibration.py
    report_builder.py
  engine/
    event_loop.py
    multi_instrument_scheduler.py
  viz/
    streamlit_v2.py
  monitor/
    drift_alerts.py
    risk_usage.py
  tests/
    ...
```

---

## 17. Core Pseudocode Snippets

### 17.1 Event Loop (Simplified)
```python
for bar in bars:
    update_intraday_state(bar)

    if not or_primary.finalized:
        continue

    if not state_assigned:
        auction_state = classify_auction_state(context_features)

    if context_exclusion_matrix.reject(context_signature):
        continue

    for playbook in active_playbooks:
        if playbook.eligibility(auction_state, features):
            signals = playbook.generate_signals(context)
            for sig in signals:
                sig = probability_gate(sig, model)
                if sig.accepted:
                    risk_mgr.open_trade(sig)

    for trade in open_trades:
        trade.update_mfe_mae(bar)
        salvage_mgr.evaluate(trade)
        trailing_mgr.evaluate(trade)
        risk_mgr.evaluate_phase_transitions(trade)
        if trade.closed:
            persist(trade)
```

### 17.2 Probability Gate
```python
p_ext = model.predict(features_for_trade)
if p_ext < p_threshold_min:
    reject("LOW_PROB")
elif mid_zone and p_ext between p_soft_floor & p_hard_floor:
    reduce_size(factor=0.5)
trade.metadata['p_extension'] = p_ext
```

### 17.3 Trailing Mode Dispatcher
```python
mode = trade.exit_mode
if mode == TRAIL_VOL:
    new_stop = price - atr(14)*k
elif mode == TRAIL_PIVOT:
    new_stop = last_confirmed_pivot - buffer
elif mode == HYBRID_VOL_PIVOT:
    new_stop = max(pivot_stop, vol_stop)
if new_stop > old_stop (long):
    update_stop(new_stop)
```

---

## 18. Deployment & Rollout Strategy

| Stage | Environment | Objective |
|-------|-------------|-----------|
| Dev | Local | Module correctness & unit tests |
| Research | Historical Backtest Harness | Parameter & exclusion matrix convergence |
| Validation | Walk-forward (multi-slice) | Stability & drift metrics |
| Pre-Paper | Dry-run real-time simulation (delayed data) | Latency & state correctness |
| Paper | Live feed → simulation orders | Execution fidelity |
| Transition | Micro live small-size | Real slippage & fill variance |
| Scale | Incremental contract sizing | Risk parity with capital growth |

---

## 19. Documentation & Knowledge Base

| Doc | Content |
|-----|---------|
| `IMPLEMENTATION_DETAIL.md` | (This spec) |
| `PLAYBOOKS.md` | Detailed logic & parameter decisions |
| `RISK_ENGINE.md` | Two-phase + salvage specification |
| `EXTENSION_MODEL.md` | Feature list, modeling approach, calibration notes |
| `ANALYTICS_GUIDE.md` | How to interpret reports & drift alerts |
| `RUNBOOK.md` | Operational tasks, how to restart simulation, failure handling |
| `CHANGELOG.md` | Versioned diffs of parameter & structural changes |

---

## 20. Acceptance Final Checklist (Go/No-Go for Paper)

| Item | Requirement | Status |
|------|-------------|--------|
| Data Integrity | 30 random day audits pass | Pending |
| Auction State Separation | Conditional expectancy separation significant (p < 0.05) | Pending |
| Two-Phase Stop vs Baseline | Avg loss reduction ≥ 15% | Pending |
| Playbook ORB 2.0 | Positive or near-positive standalone | Pending |
| Salvage Net Benefit | Salvage expectancy uplift > 0 | Pending |
| Exclusion Net Gain | Expectancy + Δ > 0.03R vs no exclusion | Pending |
| Calibration Reliability | Max bucket error < 0.15 | Pending |
| Engine Determinism | Seeded run reproducible 100% | Pending |
| Risk Guard Compliance | No daily rule violations in 3M hist sim | Pending |

---

## 21. Immediate Next Action Selection

Declare initial implementation focus (choose):  
`S1_FEATURES` | `S2_AUCTION_STATE` | `S3_EXCLUSION_MATRIX` | `S4_RISK_STOP_SALVAGE` | `S5_PB1_REFACTOR` | `FULL_PIPELINE`

Respond with the code for one of the above and we will generate task breakdown + starter stubs.

---

## 22. Closing Summary

You now have a precise spec to:

1. **Re-engineer ORB** from a static breakout tool → adaptive, probabilistic, multi-tactic engine.  
2. **Align exits with context** instead of forcing uniform partial logic.  
3. **Control downside asymmetry** via two-phase stops & salvage.  
4. **Select only statistically productive contexts** with an exclusion matrix.  
5. **Add long-term resilience** through drift detection & regime adaptation.  

This document should remain the single source of truth. All development increments must cite the section & requirement they implement.

---

*End of Implementation Specification*  