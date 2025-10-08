# ORB Confluence Breakout Trading Strategy – Technical Specification (Free / Zero‑Cost Development Track)

Version: 1.1 (Free Implementation Variant)  
Previous Version: 1.0 (Full / Vendor‑Data Oriented)  
Focus: Implement the strategy using ONLY free / open data sources, open‑source libraries, and no recurring vendor costs until the edge is validated.  
Scope: Prototype, research, and validate logic; prepare architecture so that later swapping in paid low‑latency futures feeds is frictionless.

---

## 1. Purpose (Unchanged Strategy, Different Resourcing)

We keep the original ORB Confluence logic (adaptive Opening Range + multi‑factor breakout confirmation + governance) but replace all paid dependencies with:
- Free data (proxies, synthetic generation, public APIs with free tiers).
- Open‑source tooling for computation, charting, optimization, visualization.
- Public domain or permissively licensed libraries only.

Goal: Reach a robust, validated research prototype (statistical edge, reproducible pipeline) BEFORE incurring any data or infra spend.

---

## 2. Instrument Strategy vs Free Development Reality

Real target instruments (futures): ES/MES, NQ/MNQ, CL/MCL, GC/MGC, 6E/M6E.  
Free development substitutes (symbol proxies):

| Futures Target | Interim Free Proxy (Reason) | Data Source (Free) | Notes / Limitations |
|----------------|-----------------------------|--------------------|---------------------|
| ES (S&P 500) | SPY or ^GSPC (index) | Yahoo Finance | Equity ETF opens 08:30 CT (sync to futures RTH minus pre-market differences). |
| NQ (Nasdaq 100) | QQQ or ^NDX | Yahoo Finance | Higher volatility retained; ETF volume ≠ futures volume scale—use relative metrics only. |
| CL (Crude Oil) | USO (ETF) | Yahoo Finance | USO lags front oil futures; intraday structure approximate only. |
| GC (Gold) | GLD | Yahoo Finance | Similar caution: ETF creation/redemption & equity exchange hours. |
| 6E (Euro FX) | EURUSD spot | Free FX (Stooq / Alpha Vantage) | Spot trades nearly 24h; build session filter to mimic CME RTH slice. |
| Universal Alt | BTCUSDT perpetual | Binance Public API | Free high‑resolution intraday—use to stress test breakout logic in high vol environment. |
| Synthetic | Programmatically generated bar sets | Custom generator | Use to test edge-case OR widths, volatility regimes, factor gating. |

*Rationale:* Use ETFs / spot / crypto to develop generic OR/factor engine; decouple microstructure specifics initially.

---

## 3. Free Data Sources & Access Paths

| Source | Type | Frequency | Access Method | Limits | Notes |
|--------|------|-----------|---------------|--------|------|
| Yahoo Finance | Stocks / ETFs / Indices | 1m (back ~30d), 5m+ longer | yfinance (Python) | Historical intraday depth limited | Cache locally daily to prevent gaps. |
| Stooq | Daily + some intraday (varies) | Mostly EOD | stooq CSV | No intraday minute for all tickers | Use for prior day structure proxies (fallback). |
| Alpha Vantage | FX / Crypto / Equities | 1min (5 calls/min) | alpha_vantage pkg / requests | Rate-limited | Use for EURUSD + backup. |
| Binance (public) | Crypto (spot & futures) | 1m+ unlimited | REST `/klines` | Weight-based rate limits | Great for high-volume test sets. |
| Coinbase | Crypto spot | 1m+ | REST `/products/{}/candles` | Rate-limited | Alternative crypto feed. |
| Polygon (OPTIONAL free tier) | Limited equities/forex | 1min | REST | Daily call cap | Only if needed; avoid if “no costs” is strict. |
| HistData.com (manual) | FX (CSV) | 1m | Manual download | Manual labor | Use for offline test packs. |
| Synthetic Generator | Custom | Any | Local script | None | Build stress scenarios (super narrow / wide OR). |

**Storage:** Convert everything to a unified minute bar schema, save to Parquet in `/data/raw/free/`.  

---

## 4. Open‑Source Python Stack (All Free)

| Concern | Library |
|---------|---------|
| Data Handling | pandas, polars (optional), pyarrow |
| Math / Vectorization | numpy, numba |
| TA (selective) | pandas-ta (or write minimal functions manually) |
| Optimization | optuna |
| Plotting (Python layer) | plotly, bokeh, mplfinance |
| Dashboards (Phase 1 internal) | jupyter + voila OR simple Streamlit (free) |
| Static Reports | Jinja2 + WeasyPrint / pure HTML export |
| Config | pydantic, ruamel.yaml |
| Logging | loguru or structlog |
| Testing | pytest, hypothesis |
| Packaging | poetry or hatch |
| Lint/Format | ruff, black, isort |
| CI (optional local) | pre-commit hooks only (no paid CI) |

No paid dependencies required. Avoid TA-Lib C dependency unless needed.

---

## 5. Front-End (Phase 2) Free Stack

| Layer | Option (Free OSS) | Notes |
|-------|-------------------|-------|
| Framework | React + TypeScript (Vite) | MIT environment |
| Components | Headless UI / Chakra UI / Tailwind | Styling speed |
| Charting | TradingView Lightweight Charts (free), Plotly.js, Apache ECharts | Lightweight Charts good for price; Plotly for multi-dimensional panels |
| State Management | Zustand or Redux Toolkit | Minimal overhead |
| API Bridge | FastAPI (Python) -> REST + WebSocket | Single container deploy |
| Auth (optional later) | FastAPI simple JWT (pyjwt) | Only if multi-user |
| Build / Deploy | Docker + local run (no hosted unless free local env) | Keep portability |

---

## 6. Strategy Logic (Unchanged Core)

### 6.1 Opening Range
- Adaptive: 10/15/30 selection based on normalized volatility (intraday ATR / daily ATR from proxy data).
- OR validity filter still applied; when using proxies, log distortion flag: `instrument_mode = proxy`.

### 6.2 Breakout Thresholds
- Buffer = fixed + optional ATR fraction.
- For crypto (BTCUSDT), define distinct default buffers (e.g., 0.1% of price or ATR multiple) to remain scale-free.

### 6.3 Factors (Same definitions)
| Factor | Implementation Adaptations for Free Data |
|--------|-------------------------------------------|
| Relative Volume | Use relVol = vol / SMA(vol, n). For proxies with ETF midday volume shape, test using volume z-score variant. |
| Price Action | Use aggregated minute bars; optional fractal pivot detection. |
| Profile Proxy | Prior day high/low; quartiles approximated (no volume profile). |
| VWAP | Session-based starting at RTH open (ETF start). |
| ADX | Manual computed; optional skip if data length insufficient. |

### 6.4 Scoring & Governance
Identical to full design. Simply mark `data_quality` dimension in logs (OK / Limited / Synthetic).

---

## 7. Assumptions & Compromises (Free Track)

| Area | Compromise | Mitigation |
|------|------------|------------|
| Volume Fidelity | ETF volume != futures depth | Focus on relative ratios, not absolute thresholds. |
| Session Differences | ETF open may lag futures pre-market dynamics | Use strict session window; ignore pre-market. |
| Crude & Gold | ETF proxies (USO, GLD) do not reflect intraday roll behaviors | Treat performance on those proxies as *structure* validation, not edge evidence. |
| FX Spot vs Futures | 24h vs session-limited | Slice spot into synthetic CME RTH window. |
| Crypto | 24/7 volatility; no “official OR” | Define OR relative to a chosen anchor time (e.g., 13:30 UTC) for cross-asset stress tests. |
| Data Gaps (Yahoo 1m) | Backfill only ~30 days | Schedule daily archival job locally; combine with other sources after horizon reached. |

---

## 8. Synthetic Data Layer (Free Testing Power-Up)

Design a generator to create test sets:
- **Volatility Regimes:** low / medium / spike.
- **OR Width Scenarios:** extremely narrow, normal, extremely wide.
- **Event Shock Cases:** abrupt range expansion mid-session.
- **Mean-Reverting vs Trend Day Shapes:** enforce directional drift probability.

Use these to:
- Validate OR validity filter boundaries.
- Stress test governance (multiple consecutive losers).
- Ensure partial & BE shift logic integrity.

---

## 9. Data Ingestion Plan (Daily, Free)

1. At local day end (cron):
   - Pull 1m data for SPY, QQQ, USO, GLD, BTCUSDT (Binance).
2. Append to incremental Parquet dataset `/data/raw/free/{symbol}/year=YYYY/month=MM/*.parquet`.
3. Normalize schema:
   ```
   timestamp_utc, open, high, low, close, volume, symbol, source, session_flag
   ```
4. Build daily aggregated file for prior day metrics (H/L/Mid).
5. Recompute cached ATR & relVol baselines for next day.

No cloud storage required; use local disk (ext4 / NTFS). Optionally add simple hash to detect corruption.

---

## 10. Implementation Order (Free Track)

| Order | Component | Notes |
|-------|-----------|-------|
| 1 | Config schema | YAML with defaults for proxy adaptation |
| 2 | Data fetch adapters (Yahoo, Binance, Alpha Vantage minimal) | Wrap in uniform interface |
| 3 | OR builder + adaptive logic | Test with synthetic + SPY |
| 4 | Factor modules (RV, Price Action, Profile, VWAP, ADX) | Each pure functions; unit tests |
| 5 | Scoring engine | Accept factor flags & weights |
| 6 | Breakout detection | Intrabar high/low logic |
| 7 | Trade manager (stops, targets, partials, BE) | R-based only |
| 8 | Governance | Daily counters, lockout |
| 9 | Backtest driver | Sequential event loop |
| 10 | Metrics & reporting | Equity curve, OR stats, factor attribution |
| 11 | Synthetic scenario harness | Deterministic test seeds |
| 12 | Basic Jupyter dashboard / Streamlit app | Visual sanity pre-TSX frontend |
| 13 | Optimization (Optuna) | Focus on buffer, OR thresholds, score gating |
| 14 | Documentation & freeze baseline | Prep for possible paid data upgrade decision |

---

## 11. Free Optimization & Analysis

| Task | Tool | Free? | Notes |
|------|------|-------|------|
| Grid / Random search | Optuna (TPE sampler) | Yes | Uses local SQLite storage. |
| In-sample vs Out-of-sample split | pandas slicing | Yes | Simple chronological halves or k-fold by week. |
| Walk-forward test | Custom wrapper | Yes | Sliding window parameter re-fit & test. |
| Result persistence | Parquet + JSON | Yes | No DB required initially. |
| Visualization of parameter surface | plotly | Yes | 3D surfaces for 2-param sweeps. |

---

## 12. Dash / Streamlit (Phase 1 Lightweight UI)

| View | Content |
|------|---------|
| Session Replay | Candles + OR box + breakout threshold lines + trade markers |
| Confluence Panel | Factor pass matrix per trade |
| Equity & R Curve | Cumulative R, drawdown |
| OR Distribution | Histogram of ORWidth / ATR |
| Factor Impact | Bar chart: expectancy difference with vs without factor pass |
| Score Gradient | R expectancy by score bucket |

No paid hosting; run locally. TSX (React) build deferred until internal confirmation.

---

## 13. Logging & Reproducibility (No Paid Infra)

| Element | Implementation (Free) |
|---------|-----------------------|
| Run ID | UUID + timestamp + git commit hash |
| Config Snapshot | Write YAML copy to `/runs/{run_id}/config.yaml` |
| Trades Log | Parquet `/runs/{run_id}/trades.parquet` |
| Factor Matrix Sample | Limit e.g. 5% random rows for space |
| Equity Curve | `/runs/{run_id}/equity.parquet` |
| Report | HTML built via Jinja2 → `/runs/{run_id}/report.html` |
| Determinism | Set `PYTHONHASHSEED`, numpy random seed, Optuna seed |

---

## 14. Difference Table: Full vs Free Track

| Aspect | Full (Future) | Free Track Now | Upgrade Path |
|--------|---------------|----------------|--------------|
| Futures Data | Paid real-time feed | ETF / spot proxies | Swap data adapter layer |
| Volume Profile | True volume profile API | Quartile proxy (price only) | Add profile module injection |
| Latency | Sub-second | Minute bars & batch pulls | Add streaming handler |
| Execution Model | Slippage / partial fills | Simplified bar extremes | Integrate fill simulator |
| Multi-Instrument Portfolio | Correlated risk mgmt | Single-instrument isolation runs | Add portfolio service |
| Order Flow Factors | Cumulative delta | Skipped | Plug via factor interface |
| Deployment | Server/container cluster | Local dev machine | Containerize & push |

---

## 15. Validation Milestones (Free Track)

| Milestone | Pass Criteria |
|-----------|---------------|
| OR Accuracy | Synthetic tests: all target widths produced & validated correctly |
| Factor Integrity | Each factor toggled → correct score changes logged |
| Backtest Determinism | Two runs with identical seed produce identical trades |
| Edge Indication | Score≥k trades outperform baseline raw OR breakout |
| Governance | Lockout triggers exactly at specified consecutive losses |
| Robustness | Parameter perturbation ±10% yields limited expectancy variance |
| Reporting | HTML contains: summary metrics, OR stats, factor attribution, R histograms |

---

## 16. Risk Notes (Free Implementation Context)

| Risk | Impact | Mitigation |
|------|--------|------------|
| Proxy Divergence | False edge indicated | Annotate all results “proxy mode”; replicate a subset w/ limited real futures sample later. |
| Yahoo Minute Gaps | Broken OR days | QC pre-pass: require continuous first OR window bars. |
| Crypto 24/7 Noise | Misleading OR inference | Use separate config: `instrument_mode=crypto` + distinct anchor OR time. |
| Overfitting on Small Window (e.g., 30 days) | Inflated metrics | Use synthetic extension & cross-source mixing (SPY + QQQ + BTC) to enlarge training variety. |

---

## 17. Zero‑Cost Environment Setup

```bash
# 1. Create environment
python -m venv .venv
source .venv/bin/activate

# 2. Install core libs
pip install --upgrade pip
pip install pandas numpy numba polars pyarrow plotly yfinance requests pydantic ruamel.yaml optuna loguru hypothesis pytest jinja2

# 3. Optional (Streamlit quick dashboard)
pip install streamlit

# 4. Freeze requirements
pip freeze > requirements.txt
```

---

## 18. Example Free Data Fetch (Prototype Snippet)

```python
import yfinance as yf
import pandas as pd
from datetime import datetime, timezone

def fetch_minute(symbol: str, period="30d", interval="1m") -> pd.DataFrame:
    df = yf.download(symbol, period=period, interval=interval, auto_adjust=False, progress=False)
    df = df.rename(columns=str.lower).reset_index()
    df['timestamp_utc'] = df['datetime'].dt.tz_convert(timezone.utc)
    keep = ['timestamp_utc','open','high','low','close','volume']
    df = df[keep].assign(symbol=symbol, source="yahoo")
    return df

spy = fetch_minute("SPY")
print(spy.head())
```

---

## 19. Upgrade Hooks (Design For Later, Implement Now)

| Hook Point | Interface | Later Plug-In |
|------------|-----------|---------------|
| Data Adapter | `get_bars(symbol, start, end, interval)` | Paid CME feed |
| Volume Profile | `get_value_area_levels(date, symbol)` | Real profile service |
| Order Flow | `get_delta_stream(symbol, ts_window)` | Feed aggregator |
| Execution Simulator | `simulate_fills(bar, order)` | Latency / slippage model |
| Portfolio Allocator | `allocate(trade_signal, portfolio_state)` | Risk parity / correlation filter |

Each present as stub returning “Not Implemented” or basic placeholder in free track.

---

## 20. Documentation & Transparency Flags

Add to every report:
- `DATA_MODE: FREE_PROXY`
- Symbols used + substitution mapping.
- Disclaimer: “Performance on proxy instruments may not reflect true futures microstructure or fill dynamics.”

---

## 21. Acceptance Criteria for Transition to Paid Data Phase

| Criterion | Threshold (Proxy Mode) |
|-----------|------------------------|
| OR Valid Rate | ≥ 75% of days usable after QC |
| Expectancy Stability | 3 consecutive 30‑day rolling windows all > 0 R expectancy |
| Parameter Stability | ±10% param perturbation: expectancy drawdown < 20% |
| Factor Contribution | At least 2 factors statistically significant vs random (p<0.05) |
| Governance Efficacy | Lockouts reduce peak daily drawdown vs unlocked baseline |
| Report Completeness | Automated nightly artifact generation success rate > 95% |

---

## 22. Next Actions (Free Track)

1. Approve this “free variant” specification.
2. Fetch 30d minute data for SPY, QQQ, BTCUSDT; build baseline dataset.
3. Implement OR builder + QC module (skip invalid day logging).
4. Implement factors & scoring; log raw vs scored breakout outcome comparison.
5. Run synthetic stress harness; verify boundary behavior.
6. Generate first HTML attribution report.
7. Decide pivot to adding a second governance variable (e.g., max daily R loss) if metrics warrant.

---

## 23. Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | (prior) | Original full spec |
| 1.1 | (today) | Converted to zero-cost path, added proxy mapping & free tooling plan |

---

## 24. Summary

This zero‑cost adaptation preserves strategic integrity while eliminating barriers to rapid iteration. By using ETF, spot FX, and crypto proxies plus synthetic regimes, we can:
- Harden logic,
- Validate confluence value,
- Establish deterministic pipelines,

…before spending on professional futures market data. Architecture is deliberately decoupled so an eventual transition is a data adapter swap, not a rewrite.

---

*Confirm acceptance or request additions (e.g., include explicit synthetic data generator spec, add minimal Streamlit dashboard design, or early multi-instrument correlation placeholder).*