# Streamlit Dashboard Instructions

## 🚀 Quick Start

### Installation

First, install Streamlit if not already installed:

```bash
pip install streamlit
# or with poetry:
poetry add streamlit
```

### Running the Dashboard

From the project root directory:

```bash
streamlit run streamlit_app.py
```

The dashboard will open automatically in your browser at `http://localhost:8501`

---

## 📊 Dashboard Features

### 5 Interactive Pages

1. **📊 Performance Summary**
   - Key metrics cards (Total R, Win Rate, Trades, Sharpe)
   - Detailed return and risk metrics
   - Trade statistics breakdown
   - Win/loss analysis

2. **📈 Equity Curve & Drawdown**
   - Interactive cumulative returns chart
   - Drawdown visualization
   - Final equity and max drawdown metrics
   - Hover details on each trade

3. **📋 Trades Table**
   - Sortable, filterable trade history
   - Filter by direction (long/short)
   - Filter by outcome (winners/losers)
   - R-range slider
   - Download filtered trades as CSV

4. **🎯 Factor Attribution**
   - Factor presence vs performance analysis
   - Delta metrics (impact when present vs absent)
   - Interactive bar charts
   - Score bucket performance analysis
   - Win rate by confluence score

5. **📏 OR Distribution**
   - Opening Range width distribution
   - OR width vs performance scatter plot
   - Statistical analysis
   - Correlation metrics

---

## 📁 Data Format

The dashboard expects backtest results in the `runs/` directory:

```
runs/
├── backtest_20240102/
│   ├── trades.parquet          # Trade history
│   ├── equity_curve.parquet    # Equity curve data
│   ├── factor_snapshots.parquet # Factor data
│   ├── config.json             # Strategy config
│   ├── metrics.json            # Performance metrics
│   └── report.html             # HTML report
```

### Required Files

**Minimum:**
- `trades.parquet` or `trades.csv`
- `equity_curve.parquet` or `equity_curve.csv`

**Optional (for enhanced features):**
- `metrics.json` - Pre-computed metrics
- `config.json` - Strategy configuration
- `factor_snapshots.parquet` - Factor analysis

### Data Schemas

**trades.parquet:**
```python
{
    'trade_id': str,
    'direction': str,           # 'long' or 'short'
    'entry_timestamp': datetime,
    'exit_timestamp': datetime,
    'entry_price': float,
    'exit_price': float,
    'realized_r': float,        # Required
    'max_favorable_r': float,
    'max_adverse_r': float,
    'exit_reason': str,
    'or_high': float,           # Optional
    'or_low': float,            # Optional
    'confluence_score': float,  # Optional
    'factor_*': bool,          # Optional factor flags
}
```

**equity_curve.parquet:**
```python
{
    'trade_number': int,
    'cumulative_r': float,      # Required
    'drawdown_r': float,        # Required
    'drawdown_pct': float,      # Optional
}
```

**metrics.json:**
```json
{
    "total_trades": 100,
    "winning_trades": 60,
    "losing_trades": 40,
    "win_rate": 0.6,
    "total_r": 15.5,
    "average_r": 0.155,
    "median_r": 0.12,
    "expectancy": 0.155,
    "profit_factor": 2.3,
    "sharpe_ratio": 1.8,
    "sortino_ratio": 2.1,
    "max_drawdown_r": -3.2,
    "max_drawdown_pct": -15.5,
    "avg_winner_r": 0.45,
    "avg_loser_r": -0.3,
    "largest_winner_r": 2.1,
    "largest_loser_r": -1.2,
    "consecutive_wins": 7,
    "consecutive_losses": 4
}
```

---

## 💡 Saving Backtest Results

### Example: Save Results for Dashboard

```python
from orb_confluence.config import load_config
from orb_confluence.data import YahooProvider
from orb_confluence.backtest import EventLoopBacktest
from orb_confluence.analytics import compute_metrics, compute_equity_curve
from orb_confluence.reporting import generate_report
from pathlib import Path
import pandas as pd
import json

# Run backtest
config = load_config("config.yaml")
bars = YahooProvider().fetch_intraday('SPY', '2024-01-02', '2024-01-10', '1m')

engine = EventLoopBacktest(config)
result = engine.run(bars)

# Create run directory
run_id = 'spy_20240102'
run_dir = Path('runs') / run_id
run_dir.mkdir(parents=True, exist_ok=True)

# 1. Save trades
trades_df = pd.DataFrame([
    {
        'trade_id': t.trade_id,
        'direction': t.direction,
        'entry_timestamp': t.entry_timestamp,
        'exit_timestamp': t.exit_timestamp,
        'entry_price': t.entry_price,
        'exit_price': t.exit_price,
        'realized_r': t.realized_r,
        'max_favorable_r': t.max_favorable_r,
        'max_adverse_r': t.max_adverse_r,
        'exit_reason': t.exit_reason,
        # Add OR data if available
        'or_high': t.signal.or_high if t.signal else None,
        'or_low': t.signal.or_low if t.signal else None,
        'confluence_score': t.signal.confluence_score if t.signal else None,
        # Add factor flags
        **{f'factor_{k}': v for k, v in t.signal.factors.items()} if t.signal else {},
    }
    for t in result.trades
])
trades_df.to_parquet(run_dir / 'trades.parquet')

# 2. Save equity curve
equity_df = compute_equity_curve(result.trades)
equity_df.to_parquet(run_dir / 'equity_curve.parquet')

# 3. Save metrics
metrics = compute_metrics(result.trades)
metrics_dict = {
    'total_trades': metrics.total_trades,
    'winning_trades': metrics.winning_trades,
    'losing_trades': metrics.losing_trades,
    'win_rate': metrics.win_rate,
    'total_r': metrics.total_r,
    'average_r': metrics.average_r,
    'median_r': metrics.median_r,
    'expectancy': metrics.expectancy,
    'profit_factor': metrics.profit_factor,
    'sharpe_ratio': metrics.sharpe_ratio,
    'sortino_ratio': metrics.sortino_ratio,
    'max_drawdown_r': metrics.max_drawdown_r,
    'max_drawdown_pct': metrics.max_drawdown_pct,
    'avg_winner_r': metrics.avg_winner_r,
    'avg_loser_r': metrics.avg_loser_r,
    'largest_winner_r': metrics.largest_winner_r,
    'largest_loser_r': metrics.largest_loser_r,
    'consecutive_wins': metrics.consecutive_wins,
    'consecutive_losses': metrics.consecutive_losses,
}
with open(run_dir / 'metrics.json', 'w') as f:
    json.dump(metrics_dict, f, indent=2)

# 4. Generate HTML report
html = generate_report(result, config, output_path=run_dir / 'report.html')

print(f"Results saved to: {run_dir}")
print(f"View in dashboard: streamlit run streamlit_app.py")
```

---

## 🎨 Customization

### Modify Page Layout

Edit `streamlit_app.py` and adjust the page functions:
- `page_summary()` - Metrics display
- `page_equity_curve()` - Charts
- `page_trades_table()` - Filters and columns
- `page_factor_attribution()` - Factor analysis
- `page_or_distribution()` - OR visualization

### Add New Charts

Use Plotly for interactive charts:

```python
import plotly.graph_objects as go

fig = go.Figure()
fig.add_trace(go.Scatter(x=data['x'], y=data['y']))
st.plotly_chart(fig, use_container_width=True)
```

### Change Theme

Create `.streamlit/config.toml`:

```toml
[theme]
primaryColor = "#3498DB"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F0F2F6"
textColor = "#262730"
font = "sans serif"
```

---

## 🔧 Troubleshooting

### Port Already in Use

```bash
streamlit run streamlit_app.py --server.port 8502
```

### No Data Showing

1. Check that `runs/` directory exists
2. Verify parquet files are present
3. Check file formats match schema
4. Look for errors in terminal

### Slow Loading

- Use parquet instead of CSV
- Reduce data size (filter date ranges)
- Increase caching limits in `st.cache_data`

### Import Errors

```bash
# Install required packages
pip install streamlit plotly pandas
```

---

## 📈 Performance Tips

1. **Use Parquet**: 10x faster than CSV
   ```python
   df.to_parquet('trades.parquet')  # Instead of CSV
   ```

2. **Enable Caching**: Already implemented with `@st.cache_data`

3. **Limit Data**: Filter to recent runs for faster loading

4. **Optimize Charts**: Use `plotly` instead of matplotlib for better performance

---

## 🚀 Deployment

### Deploy to Streamlit Cloud

1. Push code to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your repository
4. Deploy!

### Run in Production

```bash
streamlit run streamlit_app.py --server.port 8501 --server.address 0.0.0.0
```

---

## 📚 Additional Resources

- [Streamlit Documentation](https://docs.streamlit.io)
- [Plotly Documentation](https://plotly.com/python/)
- [Pandas Documentation](https://pandas.pydata.org/docs/)

---

**Status**: ✅ Production Ready  
**Version**: 1.0  
**Last Updated**: 2024  

Happy analyzing! 📊🚀
