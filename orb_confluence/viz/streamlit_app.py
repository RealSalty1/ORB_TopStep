"""Streamlit dashboard for ORB strategy analysis."""

import sys
from pathlib import Path
from datetime import datetime

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import json

# Import multi-instrument pages
from multi_instrument_pages import (
    page_multi_instrument_overview,
    page_pre_session_rankings
)
from enhanced_charts_page import page_charts_enhanced
from orb2_analysis_page import page_orb2_analysis

# Page config
st.set_page_config(
    page_title="ORB Strategy Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    .metric-card {
        background-color: #1e1e1e;
        padding: 20px;
        border-radius: 10px;
        border: 1px solid #333;
    }
    .stMetric {
        background-color: #2e2e2e;
        padding: 10px;
        border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_data
def load_runs():
    """Load available backtest runs."""
    runs_dir = Path("runs")
    if not runs_dir.exists():
        return []
    
    runs = []
    for run_path in runs_dir.iterdir():
        # Include any directory that has backtest data
        # Old format: summary.json or all_trades.json
        # New ORB 2.0 format: metrics.json and trades.parquet
        if run_path.is_dir():
            has_data = (
                (run_path / "summary.json").exists() or 
                (run_path / "all_trades.json").exists() or
                (run_path / "metrics.json").exists()
            )
            if has_data:
                runs.append(run_path.name)
    
    return sorted(runs, reverse=True)


@st.cache_data
def load_futures_data():
    """Load cached futures data from JSON files (checks databento_1m first, then futures_1m)."""
    # Try databento first (5 years of data), fallback to futures_1m
    cache_dirs = [
        Path("data_cache/databento_1m"),
        Path("data_cache/futures_1m")
    ]
    
    futures_data = {}
    
    for cache_dir in cache_dirs:
        if not cache_dir.exists():
            continue
            
        for json_file in cache_dir.glob("*.json"):
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                
                # Check if it's databento format (simpler structure)
                if isinstance(data, list):
                    # Databento format: list of bars
                    symbol = json_file.stem.replace('_1m', '').replace('_15m', '')
                    df = pd.DataFrame(data)
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    
                    futures_data[symbol] = {
                        'display_name': f"{symbol} Futures (Databento)",
                        'yahoo_symbol': symbol,
                        'interval': '1m',
                        'bar_count': len(df),
                        'data': df,
                        'fetch_timestamp': df['timestamp'].max().isoformat() if len(df) > 0 else None,
                        'source': 'databento'
                    }
                else:
                    # Yahoo format: dict with metadata
                    symbol = data['symbol']
                    df = pd.DataFrame(data['data'])
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    
                    futures_data[symbol] = {
                        'display_name': data['display_name'],
                        'yahoo_symbol': data['yahoo_symbol'],
                        'interval': data['interval'],
                        'bar_count': data['bar_count'],
                        'data': df,
                        'fetch_timestamp': data['fetch_timestamp'],
                        'source': 'yahoo'
                    }
            except Exception as e:
                st.error(f"Error loading {json_file.name}: {e}")
                continue
        
        # If we found data, don't try the fallback
        if futures_data:
            break
    
    return futures_data


@st.cache_data
def load_run_data(run_id):
    """Load data for a specific run."""
    run_path = Path("runs") / run_id
    
    data = {
        'run_id': run_id,
        'trades': None,
        'equity': None,
        'metrics': None,
        'config': None,
    }
    
    # Check format: ORB 2.0 (metrics.json), multi-instrument (all_trades.json), or single (summary.json)
    is_orb2 = (run_path / "metrics.json").exists() and (run_path / "trades.parquet").exists()
    is_multi_instrument = (run_path / "all_trades.json").exists()
    
    if is_orb2:
        # Load ORB 2.0 format
        with open(run_path / "metrics.json", 'r') as f:
            metrics_data = json.load(f)
        
        # Load trades from parquet
        trades_df = pd.read_parquet(run_path / "trades.parquet")
        
        # Parse timestamps flexibly (handle various formats including microseconds)
        if 'entry_timestamp' in trades_df.columns:
            trades_df['entry_ts'] = pd.to_datetime(trades_df['entry_timestamp'], utc=True, errors='coerce')
            trades_df = trades_df.drop(columns=['entry_timestamp'])
        
        if 'exit_timestamp' in trades_df.columns:
            trades_df['exit_ts'] = pd.to_datetime(trades_df['exit_timestamp'], utc=True, errors='coerce')
            trades_df = trades_df.drop(columns=['exit_timestamp'])
        
        # Ensure other required columns exist for compatibility
        if 'instrument' not in trades_df.columns and 'symbol' in trades_df.columns:
            trades_df['instrument'] = trades_df['symbol']
        
        data['trades'] = trades_df
        data['metrics'] = metrics_data
        
        return data
    
    is_multi_instrument = (run_path / "all_trades.json").exists()
    
    if is_multi_instrument:
        # Load multi-instrument JSON format
        trades_file = run_path / "all_trades.json"
        if trades_file.exists():
            with open(trades_file, 'r') as f:
                trades_data = json.load(f)
                if trades_data:
                    # Flatten the nested structure for dashboard compatibility
                    flattened_trades = []
                    for trade in trades_data:
                        flat_trade = {
                            'trade_id': trade.get('trade_id'),
                            'instrument': trade.get('instrument'),
                            'symbol': trade.get('instrument'),  # Alias
                            'date': trade.get('date'),
                            
                            # Breakout context
                            'direction': trade.get('breakout_context', {}).get('direction', 'UNKNOWN'),
                            'entry_price': trade.get('risk_metrics', {}).get('entry_price', 0),
                            'entry_ts': trade.get('breakout_context', {}).get('breakout_ts'),
                            
                            # Risk
                            'stop_price': trade.get('risk_metrics', {}).get('initial_stop_price', 0),
                            'position_size': trade.get('risk_metrics', {}).get('position_size', 0),
                            'dollar_risk': trade.get('risk_metrics', {}).get('dollar_risk', 0),
                            
                            # Outcome
                            'exit_price': trade.get('outcome', {}).get('exit_price', 0),
                            'exit_ts': trade.get('outcome', {}).get('exit_ts'),
                            'exit_reason': trade.get('outcome', {}).get('exit_reason', 'unknown'),
                            'realized_r': trade.get('outcome', {}).get('realized_r_multiple', 0),
                            'realized_pnl': trade.get('outcome', {}).get('realized_pnl_dollars', 0),
                            'bars_held': trade.get('outcome', {}).get('bars_held', 0),
                            'time_to_1r_minutes': trade.get('outcome', {}).get('time_to_1r_minutes'),
                            'mfe_r': trade.get('outcome', {}).get('mfe_r', 0),
                            'mae_r': trade.get('outcome', {}).get('mae_r', 0),
                            
                            # OR metrics
                            'or_high': trade.get('or_metrics', {}).get('high', 0),
                            'or_low': trade.get('or_metrics', {}).get('low', 0),
                            'or_width': trade.get('or_metrics', {}).get('width', 0),
                            'or_width_norm': trade.get('or_metrics', {}).get('width_norm', 0),
                            'or_valid': trade.get('factors', {}).get('or_valid', False),
                            
                            # Volume
                            'volume_quality_score': trade.get('factors', {}).get('volume_quality_score', 0),
                            'volume_passes': trade.get('factors', {}).get('volume_passes', False),
                        }
                        flattened_trades.append(flat_trade)
                    
                    data['trades'] = pd.DataFrame(flattened_trades)
        
        # Load summary as metrics
        summary_file = run_path / "summary.json"
        if summary_file.exists():
            with open(summary_file, 'r') as f:
                data['metrics'] = json.load(f)
    else:
        # Load standard parquet format
        trades_file = run_path / "all_trades.parquet"
        if trades_file.exists():
            data['trades'] = pd.read_parquet(trades_file)
        
        # Load equity
        equity_file = run_path / "combined_equity.parquet"
        if equity_file.exists():
            data['equity'] = pd.read_parquet(equity_file)
        elif (run_path / "SPY_equity.parquet").exists():
            data['equity'] = pd.read_parquet(run_path / "SPY_equity.parquet")
        
        # Load metrics
        metrics_files = list(run_path.glob("*_metrics.json"))
        if metrics_files:
            with open(metrics_files[0], 'r') as f:
                data['metrics'] = json.load(f)
        
        # Load config
        config_file = run_path / "config.json"
        if config_file.exists():
            with open(config_file, 'r') as f:
                data['config'] = json.load(f)
    
    return data


def render_sidebar():
    """Render sidebar with run selection."""
    st.sidebar.title("🎯 ORB Strategy")
    st.sidebar.markdown("---")
    
    # Load available runs
    runs = load_runs()
    
    if not runs:
        st.sidebar.warning("No backtest runs found. Run a backtest first!")
        st.sidebar.code("python run_backtest.py --symbols SPY --start 2024-01-02 --end 2024-01-10 --synthetic")
        return None
    
    # Run selection
    selected_run = st.sidebar.selectbox(
        "📁 Select Backtest Run",
        runs,
        help="Choose a backtest run to analyze"
    )
    
    st.sidebar.markdown("---")
    
    # Load data
    data = load_run_data(selected_run)
    
    # Show quick stats
    if data['metrics']:
        st.sidebar.metric("Total Trades", data['metrics'].get('total_trades', 0))
        st.sidebar.metric("Win Rate", f"{data['metrics'].get('win_rate', 0):.1%}")
        st.sidebar.metric("Total R", f"{data['metrics'].get('total_r', 0):.2f}R")
    
    st.sidebar.markdown("---")
    st.sidebar.caption(f"Run ID: {selected_run}")
    
    return data


def page_overview(data):
    """Render overview page."""
    st.title("📊 ORB Strategy - Backtest Overview")
    
    if not data or not data['metrics']:
        st.warning("No data available for this run.")
        return
    
    metrics = data['metrics']
    
    # Key metrics row
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Total Trades",
            metrics.get('total_trades', 0),
            help="Total number of trades executed"
        )
    
    with col2:
        st.metric(
            "Win Rate",
            f"{metrics.get('win_rate', 0):.1%}",
            help="Percentage of winning trades"
        )
    
    with col3:
        st.metric(
            "Total Return",
            f"{metrics.get('total_r', 0):.2f}R",
            delta=f"{metrics.get('total_r', 0):.2f}R",
            help="Total return in R-multiples"
        )
    
    with col4:
        st.metric(
            "Sharpe Ratio",
            f"{metrics.get('sharpe_ratio', 0):.2f}",
            help="Risk-adjusted return"
        )
    
    st.markdown("---")
    
    # Additional metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Expectancy",
            f"{metrics.get('expectancy', 0):.3f}R",
            help="Average R per trade"
        )
    
    with col2:
        st.metric(
            "Max Drawdown",
            f"{metrics.get('max_drawdown_r', 0):.2f}R",
            help="Maximum drawdown in R"
        )
    
    with col3:
        wins = int(metrics.get('total_trades', 0) * metrics.get('win_rate', 0))
        st.metric(
            "Wins / Losses",
            f"{wins} / {metrics.get('total_trades', 0) - wins}"
        )
    
    with col4:
        st.metric(
            "Symbol",
            metrics.get('symbol', 'N/A')
        )
    
    # Show equity curve preview
    if data['equity'] is not None and not data['equity'].empty:
        st.markdown("---")
        st.subheader("📈 Equity Curve Preview")
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=data['equity'].index,
            y=data['equity']['cumulative_r'],
            mode='lines',
            name='Cumulative R',
            line=dict(color='#00ff88', width=2)
        ))
        
        fig.update_layout(
            template='plotly_dark',
            height=300,
            margin=dict(l=0, r=0, t=0, b=0),
            xaxis_title="Trade Number",
            yaxis_title="Cumulative R",
            showlegend=False,
        )
        
        st.plotly_chart(fig, use_container_width=True)


def page_equity(data):
    """Render equity curve page."""
    st.title("📈 Equity Curve & Drawdown")
    
    if not data or data['equity'] is None or data['equity'].empty:
        st.warning("No equity data available for this run.")
        return
    
    equity_df = data['equity'].copy()
    
    # Calculate drawdown
    running_max = equity_df['cumulative_r'].cummax()
    drawdown = equity_df['cumulative_r'] - running_max
    
    # Equity curve
    st.subheader("Cumulative Returns (R-Multiple)")
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=equity_df.index,
        y=equity_df['cumulative_r'],
        mode='lines',
        name='Cumulative R',
        line=dict(color='#00ff88', width=3),
        fill='tozeroy',
        fillcolor='rgba(0, 255, 136, 0.1)'
    ))
    
    fig.update_layout(
        template='plotly_dark',
        height=400,
        xaxis_title="Trade Number",
        yaxis_title="Cumulative R",
        hovermode='x unified',
        showlegend=False,
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Drawdown chart
    st.subheader("Drawdown")
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=equity_df.index,
        y=drawdown,
        mode='lines',
        name='Drawdown',
        line=dict(color='#ff4444', width=2),
        fill='tozeroy',
        fillcolor='rgba(255, 68, 68, 0.2)'
    ))
    
    fig.update_layout(
        template='plotly_dark',
        height=300,
        xaxis_title="Trade Number",
        yaxis_title="Drawdown (R)",
        hovermode='x unified',
        showlegend=False,
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Stats
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Max Drawdown", f"{drawdown.min():.2f}R")
    
    with col2:
        st.metric("Final Equity", f"{equity_df['cumulative_r'].iloc[-1]:.2f}R")
    
    with col3:
        st.metric("Total Trades", len(equity_df))


def page_trades(data):
    """Render trades table page."""
    st.title("📋 Trades Table")
    
    if not data or data['trades'] is None or data['trades'].empty:
        st.warning("No trade data available for this run.")
        return
    
    trades_df = data['trades'].copy()
    
    # Summary stats
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Trades", len(trades_df))
    
    with col2:
        wins = (trades_df['realized_r'] > 0).sum()
        st.metric("Wins", wins)
    
    with col3:
        losses = (trades_df['realized_r'] <= 0).sum()
        st.metric("Losses", losses)
    
    with col4:
        avg_r = trades_df['realized_r'].mean()
        st.metric("Avg R", f"{avg_r:.3f}R")
    
    st.markdown("---")
    
    # Filters
    col1, col2 = st.columns(2)
    
    with col1:
        direction_filter = st.multiselect(
            "Filter by Direction",
            options=['long', 'short'],
            default=['long', 'short']
        )
    
    with col2:
        outcome_filter = st.selectbox(
            "Filter by Outcome",
            options=['All', 'Wins Only', 'Losses Only']
        )
    
    # Apply filters
    filtered_df = trades_df.copy()
    
    if direction_filter:
        filtered_df = filtered_df[filtered_df['direction'].isin(direction_filter)]
    
    if outcome_filter == 'Wins Only':
        filtered_df = filtered_df[filtered_df['realized_r'] > 0]
    elif outcome_filter == 'Losses Only':
        filtered_df = filtered_df[filtered_df['realized_r'] <= 0]
    
    # Display table
    st.subheader(f"Showing {len(filtered_df)} of {len(trades_df)} trades")
    
    # Format for display
    display_df = filtered_df.copy()
    
    # Format timestamps
    if 'entry_timestamp' in display_df.columns:
        display_df['entry_timestamp'] = pd.to_datetime(display_df['entry_timestamp']).dt.strftime('%Y-%m-%d %H:%M')
    if 'exit_timestamp' in display_df.columns:
        display_df['exit_timestamp'] = pd.to_datetime(display_df['exit_timestamp']).dt.strftime('%Y-%m-%d %H:%M')
    
    # Format numbers
    if 'entry_price' in display_df.columns:
        display_df['entry_price'] = display_df['entry_price'].round(2)
    if 'exit_price' in display_df.columns:
        display_df['exit_price'] = display_df['exit_price'].round(2)
    if 'realized_r' in display_df.columns:
        display_df['realized_r'] = display_df['realized_r'].round(3)
    
    st.dataframe(
        display_df,
        use_container_width=True,
        height=400,
    )
    
    # Download button
    csv = filtered_df.to_csv(index=False)
    st.download_button(
        label="📥 Download CSV",
        data=csv,
        file_name=f"trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
    )
    
    # Distribution chart
    st.markdown("---")
    st.subheader("R-Multiple Distribution")
    
    fig = go.Figure()
    
    fig.add_trace(go.Histogram(
        x=filtered_df['realized_r'],
        nbinsx=20,
        marker=dict(
            color=filtered_df['realized_r'],
            colorscale='RdYlGn',
            line=dict(color='white', width=1)
        ),
        name='R Distribution'
    ))
    
    fig.update_layout(
        template='plotly_dark',
        height=300,
        xaxis_title="Realized R",
        yaxis_title="Frequency",
        showlegend=False,
    )
    
    st.plotly_chart(fig, use_container_width=True)


def page_attribution(data):
    """Render factor attribution page."""
    st.title("🔥 Factor Attribution")
    
    st.info("Factor attribution analysis requires full backtest data with factor snapshots.")
    st.markdown("---")
    
    if data and data['trades'] is not None and not data['trades'].empty:
        st.subheader("Trade Performance by Direction")
        
        trades_df = data['trades']
        
        # Performance by direction
        perf_by_direction = trades_df.groupby('direction').agg({
            'realized_r': ['count', 'sum', 'mean'],
        }).round(3)
        
        st.dataframe(perf_by_direction, use_container_width=True)
        
        # Chart
        fig = go.Figure()
        
        for direction in trades_df['direction'].unique():
            direction_trades = trades_df[trades_df['direction'] == direction]
            
            fig.add_trace(go.Box(
                y=direction_trades['realized_r'],
                name=direction.upper(),
                marker=dict(color='#00ff88' if direction == 'long' else '#ff4444')
            ))
        
        fig.update_layout(
            template='plotly_dark',
            height=400,
            yaxis_title="Realized R",
            showlegend=True,
        )
        
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("No trade data available.")


def page_distribution(data):
    """Render OR distribution page."""
    st.title("📊 Opening Range Distribution")
    
    st.info("OR distribution analysis requires full backtest data with OR snapshots.")
    st.markdown("---")
    
    if data and data['trades'] is not None and not data['trades'].empty:
        st.subheader("Trade Timing Distribution")
        
        trades_df = data['trades'].copy()
        
        if 'entry_timestamp' in trades_df.columns:
            trades_df['entry_timestamp'] = pd.to_datetime(trades_df['entry_timestamp'])
            trades_df['hour'] = trades_df['entry_timestamp'].dt.hour
            
            # Trades by hour
            hourly_counts = trades_df.groupby('hour').size()
            
            fig = go.Figure()
            
            fig.add_trace(go.Bar(
                x=hourly_counts.index,
                y=hourly_counts.values,
                marker=dict(color='#00ff88'),
                name='Trades per Hour'
            ))
            
            fig.update_layout(
                template='plotly_dark',
                height=300,
                xaxis_title="Hour of Day",
                yaxis_title="Number of Trades",
                showlegend=False,
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Performance by hour
            st.subheader("Performance by Hour")
            
            hourly_perf = trades_df.groupby('hour')['realized_r'].agg(['count', 'sum', 'mean']).round(3)
            st.dataframe(hourly_perf, use_container_width=True)
    else:
        st.warning("No trade data available.")


def get_enhanced_chart_config():
    """Get enhanced Plotly chart configuration for TradingView-style interactivity."""
    return {
        'displayModeBar': True,
        'displaylogo': False,
        'modeBarButtonsToAdd': [
            'drawline',
            'drawopenpath',
            'drawclosedpath',
            'drawcircle',
            'drawrect',
            'eraseshape'
        ],
        'modeBarButtonsToRemove': [],
        'toImageButtonOptions': {
            'format': 'png',
            'filename': 'trade_chart',
            'height': 1080,
            'width': 1920,
            'scale': 2
        }
    }


def render_all_trades_chart(data, trades_df):
    """Render all trades on a single chart with full bar data."""
    st.subheader("📊 All Trades Overview")
    
    # Try to load all bar data
    run_id = data['run_id']
    
    # Find the date range across all trades
    all_timestamps = []
    for _, trade in trades_df.iterrows():
        all_timestamps.append(pd.to_datetime(trade['entry_timestamp']))
        all_timestamps.append(pd.to_datetime(trade['exit_timestamp']))
    
    start_date = min(all_timestamps).date()
    end_date = max(all_timestamps).date()
    
    st.info(f"📅 Showing {len(trades_df)} trades from {start_date} to {end_date}")
    
    # Collect all available bar data
    all_bars_list = []
    for _, trade in trades_df.iterrows():
        trade_id = trade['trade_id']
        bars_file = Path(f"runs/{run_id}/{trade_id}_bars.parquet")
        
        if bars_file.exists():
            bars = pd.read_parquet(bars_file)
            all_bars_list.append(bars)
    
    if not all_bars_list:
        st.warning("No bar data available for trades. Cannot render chart.")
        return
    
    # Combine all bars and remove duplicates
    combined_bars = pd.concat(all_bars_list, ignore_index=True)
    combined_bars = combined_bars.drop_duplicates(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)
    
    st.success(f"✅ Loaded {len(combined_bars)} bars across all trades")
    
    # Create the main chart
    fig = go.Figure()
    
    # Add candlesticks
    fig.add_trace(go.Candlestick(
        x=combined_bars['timestamp'],
        open=combined_bars['open'],
        high=combined_bars['high'],
        low=combined_bars['low'],
        close=combined_bars['close'],
        name='Price',
        increasing_line_color='#26a69a',
        decreasing_line_color='#ef5350',
    ))
    
    # Add all trades
    colors_long = ['cyan', 'lime', 'yellow', 'orange', 'pink']
    colors_short = ['magenta', 'red', 'purple', 'brown', 'coral']
    
    for idx, trade in trades_df.iterrows():
        color_idx = idx % 5
        color = colors_long[color_idx] if trade['direction'] == 'long' else colors_short[color_idx]
        
        # Entry marker
        fig.add_trace(go.Scatter(
            x=[trade['entry_timestamp']],
            y=[trade['entry_price']],
            mode='markers',
            name=f"Entry {idx+1}",
            marker=dict(
                size=12,
                color=color,
                symbol='triangle-up' if trade['direction'] == 'long' else 'triangle-down',
                line=dict(width=2, color='white')
            ),
            showlegend=True,
            hovertemplate=f"<b>Trade {idx+1}</b><br>" +
                         f"Direction: {trade['direction'].upper()}<br>" +
                         f"Entry: ${trade['entry_price']:.2f}<br>" +
                         f"<extra></extra>"
        ))
        
        # Exit marker
        exit_color = 'lime' if trade['realized_r'] > 0 else 'red'
        fig.add_trace(go.Scatter(
            x=[trade['exit_timestamp']],
            y=[trade['exit_price']],
            mode='markers',
            name=f"Exit {idx+1}",
            marker=dict(
                size=12,
                color=exit_color,
                symbol='x',
                line=dict(width=2, color='white')
            ),
            showlegend=True,
            hovertemplate=f"<b>Trade {idx+1}</b><br>" +
                         f"Exit: ${trade['exit_price']:.2f}<br>" +
                         f"R: {trade['realized_r']:.2f}R<br>" +
                         f"<extra></extra>"
        ))
        
        # Connect entry to exit
        fig.add_trace(go.Scatter(
            x=[trade['entry_timestamp'], trade['exit_timestamp']],
            y=[trade['entry_price'], trade['exit_price']],
            mode='lines',
            name=f"Trade {idx+1} Path",
            line=dict(
                color=color,
                width=1,
                dash='dot'
            ),
            showlegend=False,
            hoverinfo='skip'
        ))
    
    # Enhanced layout with TradingView-style features
    fig.update_layout(
        template='plotly_dark',
        height=700,
        xaxis=dict(
            title="Time",
            rangeslider=dict(visible=True, thickness=0.05),  # Range slider for zooming
            type='date',
            showgrid=True,
            gridcolor='rgba(128, 128, 128, 0.2)',
            showspikes=True,  # Crosshair
            spikemode='across',
            spikesnap='cursor',
            spikecolor='white',
            spikethickness=1,
            spikedash='dot'
        ),
        yaxis=dict(
            title="Price ($)",
            showgrid=True,
            gridcolor='rgba(128, 128, 128, 0.2)',
            showspikes=True,  # Crosshair
            spikemode='across',
            spikesnap='cursor',
            spikecolor='white',
            spikethickness=1,
            spikedash='dot',
            fixedrange=False  # Allow y-axis zoom
        ),
        hovermode='x unified',
        showlegend=True,
        legend=dict(
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01,
            bgcolor='rgba(0,0,0,0.5)'
        ),
        dragmode='zoom',  # Default to zoom mode
    )
    
    # Display with enhanced config
    st.plotly_chart(fig, use_container_width=True, config=get_enhanced_chart_config())
    
    # Summary table
    st.markdown("---")
    st.subheader("📋 All Trades Summary")
    
    summary_df = trades_df[['trade_id', 'direction', 'entry_timestamp', 'exit_timestamp', 
                             'entry_price', 'exit_price', 'realized_r']].copy()
    summary_df['entry_timestamp'] = summary_df['entry_timestamp'].astype(str)
    summary_df['exit_timestamp'] = summary_df['exit_timestamp'].astype(str)
    
    st.dataframe(summary_df, use_container_width=True, hide_index=True)


def page_trade_charts(data):
    """Render individual trade charts with OHLCV, OR, entries, exits."""
    st.title("📈 Trade Charts - OHLCV with Signals")
    
    if not data or data['trades'] is None or data['trades'].empty:
        st.warning("No trade data available. Run a backtest with trades first!")
        st.info("""
        **Tip:** To generate trades, you may need to:
        - Lower confluence requirements in config
        - Use more volatile data (synthetic with high volatility)
        - Adjust buffer sizes
        """)
        return
    
    trades_df = data['trades'].copy()
    
    # View mode selector
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.info("📊 Interactive chart visualization with OHLC bars, OR zones, entry/exit points, TP/SL levels")
    
    with col2:
        view_mode = st.radio(
            "View Mode",
            ["Single Trade", "All Trades"],
            horizontal=True,
            help="View one trade at a time or all trades on one chart"
        )
    
    if view_mode == "All Trades":
        render_all_trades_chart(data, trades_df)
        return
    
    # Single trade view
    # Trade selector
    trade_options = [f"Trade {i+1}: {row['direction'].upper()} @ {row['entry_timestamp']} | {row['realized_r']:.2f}R" 
                     for i, row in trades_df.iterrows()]
    
    selected_trade_idx = st.selectbox(
        "Select Trade to Visualize",
        range(len(trades_df)),
        format_func=lambda x: trade_options[x]
    )
    
    trade = trades_df.iloc[selected_trade_idx]
    
    # Try to load bar data for this trade
    run_id = data['run_id']
    trade_id = trade['trade_id']
    bars_file = Path(f"runs/{run_id}/{trade_id}_bars.parquet")
    
    has_bar_data = bars_file.exists()
    
    # Trade details
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("Direction", trade['direction'].upper())
    
    with col2:
        st.metric("Entry", f"${trade['entry_price']:.2f}")
    
    with col3:
        st.metric("Exit", f"${trade['exit_price']:.2f}")
    
    with col4:
        st.metric("Realized R", f"{trade['realized_r']:.2f}R")
    
    with col5:
        outcome_emoji = "✅" if trade['realized_r'] > 0 else "❌"
        st.metric("Outcome", outcome_emoji)
    
    st.markdown("---")
    
    if has_bar_data:
        # Load bar data
        bars_df = pd.read_parquet(bars_file)
        
        # Create candlestick chart
        st.subheader("📊 OHLCV Chart with Trade Signals")
        
        fig = go.Figure()
        
        # Candlestick
        fig.add_trace(go.Candlestick(
            x=bars_df['timestamp'],
            open=bars_df['open'],
            high=bars_df['high'],
            low=bars_df['low'],
            close=bars_df['close'],
            name='Price',
            increasing_line_color='#26a69a',
            decreasing_line_color='#ef5350',
        ))
        
        # OR Zone Rectangle (if we have OR data)
        if 'or_high' in trade and 'or_low' in trade and pd.notna(trade['or_high']):
            or_start = trade.get('or_start', bars_df['timestamp'].iloc[0])
            or_end = trade.get('or_end', bars_df['timestamp'].iloc[min(15, len(bars_df)-1)])
            
            fig.add_shape(
                type="rect",
                x0=or_start, x1=or_end,
                y0=trade['or_low'], y1=trade['or_high'],
                fillcolor="rgba(100, 100, 255, 0.2)",
                line=dict(color="rgba(100, 100, 255, 0.5)", width=2),
                layer="below",
                name="OR Zone"
            )
            
            # OR High/Low lines
            fig.add_hline(
                y=trade['or_high'],
                line=dict(color='rgba(100, 100, 255, 0.6)', width=1, dash='dash'),
                annotation_text="OR High",
                annotation_position="right"
            )
            
            fig.add_hline(
                y=trade['or_low'],
                line=dict(color='rgba(100, 100, 255, 0.6)', width=1, dash='dash'),
                annotation_text="OR Low",
                annotation_position="right"
            )
        
        # Entry price line
        fig.add_hline(
            y=trade['entry_price'],
            line=dict(color='cyan', width=2, dash='solid'),
            annotation_text=f"Entry ${trade['entry_price']:.2f}",
            annotation_position="left"
        )
        
        # Stop loss line
        if 'stop_price' in trade and pd.notna(trade['stop_price']):
            fig.add_hline(
                y=trade['stop_price'],
                line=dict(color='red', width=2, dash='dot'),
                annotation_text=f"Stop ${trade['stop_price']:.2f}",
                annotation_position="left"
            )
        
        # Target lines
        if 'target_1' in trade and pd.notna(trade['target_1']):
            fig.add_hline(
                y=trade['target_1'],
                line=dict(color='lime', width=1, dash='dot'),
                annotation_text="T1 (1.5R)",
                annotation_position="right"
            )
        
        if 'target_2' in trade and pd.notna(trade['target_2']):
            fig.add_hline(
                y=trade['target_2'],
                line=dict(color='lime', width=1, dash='dot'),
                annotation_text="T2 (2R)",
                annotation_position="right"
            )
        
        if 'target_3' in trade and pd.notna(trade['target_3']):
            fig.add_hline(
                y=trade['target_3'],
                line=dict(color='lime', width=1, dash='dot'),
                annotation_text="T3 (3R)",
                annotation_position="right"
            )
        
        # Exit price line
        fig.add_hline(
            y=trade['exit_price'],
            line=dict(color='yellow', width=2, dash='solid'),
            annotation_text=f"Exit ${trade['exit_price']:.2f}",
            annotation_position="left"
        )
        
        # Entry marker
        entry_bar = bars_df[bars_df['timestamp'] >= trade['entry_timestamp']].iloc[0] if len(bars_df[bars_df['timestamp'] >= trade['entry_timestamp']]) > 0 else None
        if entry_bar is not None:
            fig.add_trace(go.Scatter(
                x=[entry_bar['timestamp']],
                y=[trade['entry_price']],
                mode='markers',
                name='Entry',
                marker=dict(
                    size=20,
                    color='cyan',
                    symbol='triangle-up' if trade['direction'] == 'long' else 'triangle-down',
                    line=dict(width=3, color='white')
                ),
                showlegend=True
            ))
        
        # Exit marker
        exit_bar = bars_df[bars_df['timestamp'] >= trade['exit_timestamp']].iloc[0] if len(bars_df[bars_df['timestamp'] >= trade['exit_timestamp']]) > 0 else None
        if exit_bar is not None:
            fig.add_trace(go.Scatter(
                x=[exit_bar['timestamp']],
                y=[trade['exit_price']],
                mode='markers',
                name='Exit',
                marker=dict(
                    size=20,
                    color='lime' if trade['realized_r'] > 0 else 'red',
                    symbol='x',
                    line=dict(width=3, color='white')
                ),
                showlegend=True
            ))
        
        # Enhanced layout with TradingView-style features
        fig.update_layout(
            template='plotly_dark',
            height=600,
            xaxis=dict(
                title="Time",
                rangeslider=dict(visible=True, thickness=0.05),  # Range slider
                showgrid=True,
                gridcolor='rgba(128, 128, 128, 0.2)',
                showspikes=True,  # Crosshair
                spikemode='across',
                spikesnap='cursor',
                spikecolor='white',
                spikethickness=1,
                spikedash='dot'
            ),
            yaxis=dict(
                title="Price ($)",
                showgrid=True,
                gridcolor='rgba(128, 128, 128, 0.2)',
                showspikes=True,  # Crosshair
                spikemode='across',
                spikesnap='cursor',
                spikecolor='white',
                spikethickness=1,
                spikedash='dot',
                fixedrange=False  # Allow y-axis zoom
            ),
            hovermode='x unified',
            showlegend=True,
            dragmode='zoom',  # Default to zoom mode
        )
        
        st.plotly_chart(fig, use_container_width=True, config=get_enhanced_chart_config())
        
        # Volume chart
        st.subheader("📊 Volume")
        
        fig_vol = go.Figure()
        
        colors = ['green' if bars_df['close'].iloc[i] >= bars_df['open'].iloc[i] else 'red' 
                  for i in range(len(bars_df))]
        
        fig_vol.add_trace(go.Bar(
            x=bars_df['timestamp'],
            y=bars_df['volume'],
            marker_color=colors,
            name='Volume',
            showlegend=False
        ))
        
        fig_vol.update_layout(
            template='plotly_dark',
            height=200,
            xaxis=dict(
                title="Time",
                showgrid=True,
                gridcolor='rgba(128, 128, 128, 0.2)',
                showspikes=True,
                spikemode='across',
                spikesnap='cursor',
                spikecolor='white',
                spikethickness=1,
                spikedash='dot'
            ),
            yaxis=dict(
                title="Volume",
                showgrid=True,
                gridcolor='rgba(128, 128, 128, 0.2)',
                fixedrange=False
            ),
            showlegend=False,
            dragmode='zoom',
        )
        
        st.plotly_chart(fig_vol, use_container_width=True, config=get_enhanced_chart_config())
        
    else:
        # Fallback: Simple entry/exit visualization
        st.warning("⚠️ Full bar data not available for this trade. Showing simplified view.")
        
        st.subheader("Trade Timeline (Simplified)")
        
        fig = go.Figure()
        
        # Entry point
        fig.add_trace(go.Scatter(
            x=[trade['entry_timestamp']],
            y=[trade['entry_price']],
            mode='markers',
            name='Entry',
            marker=dict(
                size=15,
                color='cyan',
                symbol='triangle-up' if trade['direction'] == 'long' else 'triangle-down',
                line=dict(width=2, color='white')
            )
        ))
        
        # Exit point
        fig.add_trace(go.Scatter(
            x=[trade['exit_timestamp']],
            y=[trade['exit_price']],
            mode='markers',
            name='Exit',
            marker=dict(
                size=15,
                color='lime' if trade['realized_r'] > 0 else 'red',
                symbol='x',
                line=dict(width=2, color='white')
            )
        ))
        
        # Connect entry to exit
        fig.add_trace(go.Scatter(
            x=[trade['entry_timestamp'], trade['exit_timestamp']],
            y=[trade['entry_price'], trade['exit_price']],
            mode='lines',
            name='Trade Path',
            line=dict(
                color='lime' if trade['realized_r'] > 0 else 'red',
                width=2,
                dash='dash'
            )
        ))
        
        fig.update_layout(
            template='plotly_dark',
            height=400,
            xaxis=dict(
                title="Time",
                showgrid=True,
                gridcolor='rgba(128, 128, 128, 0.2)',
                showspikes=True,
                spikecolor='white'
            ),
            yaxis=dict(
                title="Price ($)",
                showgrid=True,
                gridcolor='rgba(128, 128, 128, 0.2)',
                fixedrange=False
            ),
            hovermode='closest',
            showlegend=True,
            dragmode='zoom',
        )
        
        st.plotly_chart(fig, use_container_width=True, config=get_enhanced_chart_config())
    
    # Trade details table
    st.markdown("---")
    st.subheader("📋 Trade Details")
    
    col_left, col_right = st.columns(2)
    
    with col_left:
        # Convert timestamps to strings to avoid Arrow serialization errors
        entry_time_str = str(pd.to_datetime(trade['entry_timestamp']))
        
        details_left = {
            'Trade ID': str(trade['trade_id']),
            'Direction': str(trade['direction']).upper(),
            'Entry Time': entry_time_str,
            'Entry Price': f"${float(trade['entry_price']):.2f}",
            'Realized R': f"{float(trade['realized_r']):.3f}R",
        }
        
        if 'exit_reason' in trade:
            details_left['Exit Reason'] = str(trade['exit_reason'])
        
        details_df_left = pd.DataFrame(list(details_left.items()), columns=['Field', 'Value'])
        st.dataframe(details_df_left, use_container_width=True, hide_index=True)
    
    with col_right:
        # Convert timestamps to strings to avoid Arrow serialization errors
        exit_time_str = str(pd.to_datetime(trade['exit_timestamp']))
        duration = pd.to_datetime(trade['exit_timestamp']) - pd.to_datetime(trade['entry_timestamp'])
        
        details_right = {
            'Exit Time': exit_time_str,
            'Exit Price': f"${float(trade['exit_price']):.2f}",
            'Duration': str(duration),
        }
        
        if 'stop_price' in trade and pd.notna(trade['stop_price']):
            details_right['Stop Price'] = f"${float(trade['stop_price']):.2f}"
        
        if 'or_high' in trade and pd.notna(trade['or_high']):
            details_right['OR High'] = f"${float(trade['or_high']):.2f}"
            details_right['OR Low'] = f"${float(trade['or_low']):.2f}"
        
        details_df_right = pd.DataFrame(list(details_right.items()), columns=['Field', 'Value'])
        st.dataframe(details_df_right, use_container_width=True, hide_index=True)


def page_charts():
    """Page for viewing full futures price charts with ORB and trade overlays."""
    # Load futures data
    futures_data = load_futures_data()
    
    # Call the enhanced charts page
    page_charts_enhanced(futures_data, load_runs, get_enhanced_chart_config)
    return
    
    if not futures_data:
        st.warning("⚠️ No cached futures data found!")
        st.info("Run the data fetch script first:")
        st.code("python scripts/fetch_futures_data.py", language="bash")
        return
    
    # Asset selector
    st.markdown("### Select Futures Contract")
    
    col1, col2 = st.columns([1, 3])
    
    with col1:
        symbols = sorted(futures_data.keys())
        selected_symbol = st.selectbox(
            "Symbol",
            symbols,
            format_func=lambda x: f"{x} - {futures_data[x]['display_name']}"
        )
    
    if selected_symbol:
        contract_info = futures_data[selected_symbol]
        df = contract_info['data']
        
        # Display contract info
        with col2:
            st.markdown(f"""
            **{contract_info['display_name']}** ({contract_info['yahoo_symbol']})  
            📊 {contract_info['bar_count']:,} bars | ⏱️ {contract_info['interval']} intervals  
            📅 {df['timestamp'].min().strftime('%Y-%m-%d')} to {df['timestamp'].max().strftime('%Y-%m-%d')}
            """)
        
        st.markdown("---")
        
        # Display stats
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("Current Price", f"${df.iloc[-1]['close']:.2f}")
        
        with col2:
            price_change = df.iloc[-1]['close'] - df.iloc[0]['close']
            price_change_pct = (price_change / df.iloc[0]['close']) * 100
            st.metric("Period Change", f"${price_change:.2f}", f"{price_change_pct:+.2f}%")
        
        with col3:
            st.metric("Period High", f"${df['high'].max():.2f}")
        
        with col4:
            st.metric("Period Low", f"${df['low'].min():.2f}")
        
        with col5:
            avg_volume = df['volume'].mean()
            st.metric("Avg Volume", f"{avg_volume:,.0f}")
        
        st.markdown("---")
        
        # Create candlestick chart
        st.markdown("### Price Chart")
        
        fig = go.Figure()
        
        # Add candlesticks
        fig.add_trace(go.Candlestick(
            x=df['timestamp'],
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name=selected_symbol,
            increasing_line_color='#26a69a',
            decreasing_line_color='#ef5350',
            increasing_fillcolor='#26a69a',
            decreasing_fillcolor='#ef5350',
        ))
        
        # Update layout with TradingView-style interactivity
        chart_config = get_enhanced_chart_config()
        
        fig.update_layout(
            title=f"{contract_info['display_name']} ({selected_symbol}) - 15 Minute Chart",
            xaxis_title="Date/Time",
            yaxis_title="Price ($)",
            height=700,
            template="plotly_dark",
            xaxis=dict(
                rangeslider=dict(visible=True),
                type="date",
                showgrid=True,
                gridcolor='#2a2a2a',
                rangebreaks=[
                    # Hide weekends (Friday 5 PM to Sunday 6 PM ET)
                    dict(bounds=["sat", "mon"], pattern="day of week"),
                    # Hide daily maintenance window (5 PM - 6 PM ET = 21:00 - 22:00 UTC)
                    # Futures have a brief break each day
                    dict(bounds=[21, 22], pattern="hour"),
                ]
            ),
            yaxis=dict(
                showgrid=True,
                gridcolor='#2a2a2a',
                side='right',
            ),
            hovermode='x unified',
            showlegend=True,
            legend=dict(
                yanchor="top",
                y=0.99,
                xanchor="left",
                x=0.01
            )
        )
        
        st.plotly_chart(fig, use_container_width=True, config=chart_config)
        
        # Volume chart
        st.markdown("### Volume")
        
        fig_volume = go.Figure()
        
        # Color volume bars based on price direction
        colors = ['#26a69a' if df.iloc[i]['close'] >= df.iloc[i]['open'] else '#ef5350' 
                  for i in range(len(df))]
        
        fig_volume.add_trace(go.Bar(
            x=df['timestamp'],
            y=df['volume'],
            name='Volume',
            marker_color=colors,
        ))
        
        fig_volume.update_layout(
            title="Volume",
            xaxis_title="Date/Time",
            yaxis_title="Volume",
            height=250,
            template="plotly_dark",
            xaxis=dict(
                type="date",
                showgrid=True,
                gridcolor='#2a2a2a',
                rangebreaks=[
                    # Hide weekends (Friday 5 PM to Sunday 6 PM ET)
                    dict(bounds=["sat", "mon"], pattern="day of week"),
                    # Hide daily maintenance window (5 PM - 6 PM ET = 21:00 - 22:00 UTC)
                    dict(bounds=[21, 22], pattern="hour"),
                ]
            ),
            yaxis=dict(
                showgrid=True,
                gridcolor='#2a2a2a',
            ),
            showlegend=False,
        )
        
        st.plotly_chart(fig_volume, use_container_width=True, config=chart_config)
        
        # Data table (sample)
        with st.expander("📊 View Data Table (Last 100 bars)"):
            display_df = df.tail(100)[['timestamp', 'open', 'high', 'low', 'close', 'volume']].copy()
            display_df['timestamp'] = display_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
            st.dataframe(display_df, use_container_width=True, hide_index=True)
        
        # Download button
        st.markdown("---")
        st.markdown("### Export Data")
        
        csv = df.to_csv(index=False)
        st.download_button(
            label=f"📥 Download {selected_symbol} Data (CSV)",
            data=csv,
            file_name=f"{selected_symbol}_15m_{df['timestamp'].min().strftime('%Y%m%d')}_{df['timestamp'].max().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )


def main():
    """Main application."""
    # Sidebar
    data = render_sidebar()
    
    # Check if we're on the Charts page (which doesn't need run data)
    page = st.sidebar.radio(
        "📍 Navigation",
        ["Overview", "ORB 2.0 Analysis", "Equity Curve", "Trades Table", "Factor Attribution", "OR Distribution", "Charts", "Multi-Instrument", "Pre-Session Rankings"],
        label_visibility="visible"
    )
    
    # Charts page doesn't need run data
    if page == "Charts":
        page_charts()
        return
    
    # ORB 2.0 Analysis page
    if page == "ORB 2.0 Analysis":
        if data is None or data.get('trades') is None:
            st.title("📊 ORB 2.0 Strategy Analysis")
            st.info("👈 Select an ORB 2.0 backtest run from the sidebar to view detailed strategy analysis")
            return
        page_orb2_analysis(data)
        return
    
    # Multi-instrument pages
    if page == "Multi-Instrument":
        if data is None or 'run_id' not in data:
            st.title("🌐 Multi-Instrument Overview")
            st.info("👈 Select a backtest run from the sidebar to view multi-instrument analysis")
            return
        page_multi_instrument_overview(data['run_id'])
        return
    
    if page == "Pre-Session Rankings":
        if data is None or 'run_id' not in data:
            st.title("🏆 Pre-Session Rankings")
            st.info("👈 Select a backtest run from the sidebar to view pre-session rankings")
            return
        page_pre_session_rankings(data['run_id'])
        return
    
    if data is None:
        st.title("📊 ORB Strategy Dashboard")
        st.info("👈 Select a backtest run from the sidebar to get started")
        st.markdown("---")
        st.markdown("""
        ### Getting Started
        
        1. Run a backtest:
        ```bash
        python run_backtest.py --symbols SPY --start 2024-01-02 --end 2024-01-10 --synthetic
        ```
        
        2. Select the run from the sidebar
        
        3. Explore the interactive charts and tables
        
        ### Or View Futures Charts
        
        Navigate to the "Charts" page to view cached futures data without running a backtest!
        """)
        return
    
    # Render selected page
    if page == "Overview":
        page_overview(data)
    elif page == "Equity Curve":
        page_equity(data)
    elif page == "Trades Table":
        page_trades(data)
    elif page == "Trade Charts":
        page_trade_charts(data)
    elif page == "Factor Attribution":
        page_attribution(data)
    elif page == "OR Distribution":
        page_distribution(data)


if __name__ == "__main__":
    main()