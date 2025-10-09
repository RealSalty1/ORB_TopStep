"""
Professional TradingView-style chart page for visualizing trades.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import numpy as np
from pathlib import Path
from scipy import stats


def resample_bars(bars: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """
    Resample OHLCV bars to a different timeframe.
    
    Args:
        bars: 1-minute OHLCV data with DatetimeIndex
        timeframe: Target timeframe ('1m', '5m', '15m', '30m', '1h')
        
    Returns:
        Resampled OHLCV DataFrame
    """
    if timeframe == '1m':
        return bars
    
    # Resample
    resampled = bars.resample(timeframe).agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
    }).dropna()
    
    return resampled


def calculate_ema(bars: pd.DataFrame, period: int, column: str = 'close') -> pd.Series:
    """Calculate Exponential Moving Average."""
    return bars[column].ewm(span=period, adjust=False).mean()


def calculate_vwap(bars: pd.DataFrame) -> pd.Series:
    """Calculate Volume Weighted Average Price."""
    typical_price = (bars['high'] + bars['low'] + bars['close']) / 3
    return (typical_price * bars['volume']).cumsum() / bars['volume'].cumsum()


def calculate_bollinger_bands(bars: pd.DataFrame, period: int = 20, std: float = 2.0) -> tuple:
    """
    Calculate Bollinger Bands.
    
    Returns:
        (middle_band, upper_band, lower_band)
    """
    middle = bars['close'].rolling(window=period).mean()
    std_dev = bars['close'].rolling(window=period).std()
    upper = middle + (std_dev * std)
    lower = middle - (std_dev * std)
    
    return middle, upper, lower


def create_win_rate_heatmap(bars: pd.DataFrame, trades: pd.DataFrame, price_bins: int = 50) -> go.Figure:
    """
    Create a heatmap overlay showing win rate by price level and time.
    
    Args:
        bars: OHLCV data
        trades: Trade data with entry/exit prices and P&L
        price_bins: Number of price bins to create
        
    Returns:
        Plotly figure with heatmap
    """
    if trades.empty:
        return None
    
    # Create price bins
    price_min = bars['low'].min()
    price_max = bars['high'].max()
    price_range = np.linspace(price_min, price_max, price_bins)
    
    # Create time bins (hourly)
    trades = trades.copy()
    trades['hour'] = trades['entry_time'].dt.hour
    trades['price_level'] = pd.cut(trades['entry_price'], bins=price_range, labels=False)
    
    # Calculate win rate by hour and price level
    heatmap_data = []
    for hour in range(24):
        row = []
        for price_bin in range(len(price_range) - 1):
            hour_trades = trades[(trades['hour'] == hour) & (trades['price_level'] == price_bin)]
            if len(hour_trades) > 0:
                win_rate = (hour_trades['pnl'] > 0).sum() / len(hour_trades)
                row.append(win_rate)
            else:
                row.append(None)
        heatmap_data.append(row)
    
    # Create heatmap figure
    fig = go.Figure(data=go.Heatmap(
        z=heatmap_data,
        x=price_range[:-1],
        y=list(range(24)),
        colorscale='RdYlGn',
        zmin=0,
        zmax=1,
        colorbar=dict(title="Win Rate"),
        hovertemplate='Hour: %{y}<br>Price: %{x:.2f}<br>Win Rate: %{z:.1%}<extra></extra>',
    ))
    
    fig.update_layout(
        title="Win Rate Heatmap by Time & Price",
        xaxis_title="Price Level",
        yaxis_title="Hour of Day",
        height=400,
        template='plotly_dark',
    )
    
    return fig


def create_tradingview_chart(
    bars: pd.DataFrame,
    trades: pd.DataFrame,
    title: str = "Trade Chart",
    height: int = 800,
    show_ema_9: bool = False,
    show_ema_21: bool = False,
    show_ema_50: bool = False,
    show_vwap: bool = False,
    show_bb: bool = False,
) -> go.Figure:
    """
    Create a professional TradingView-style candlestick chart with trades overlaid.
    
    Args:
        bars: OHLCV data with DatetimeIndex
        trades: Trade data with entry/exit times and prices
        title: Chart title
        height: Chart height in pixels
        show_ema_9: Show 9-period EMA
        show_ema_21: Show 21-period EMA
        show_ema_50: Show 50-period EMA
        show_vwap: Show VWAP
        show_bb: Show Bollinger Bands
        
    Returns:
        Plotly figure with candlestick chart and trade markers
    """
    # Create continuous index to avoid gaps
    bars = bars.copy()
    bars['x_index'] = range(len(bars))
    bars['timestamp_str'] = bars.index.strftime('%Y-%m-%d %H:%M')
    
    # Create subplots: main chart + volume
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.7, 0.3],
        subplot_titles=(title, 'Volume'),
    )
    
    # Add candlestick chart with continuous x-axis
    fig.add_trace(
        go.Candlestick(
            x=bars['x_index'],
            open=bars['open'],
            high=bars['high'],
            low=bars['low'],
            close=bars['close'],
            name='Price',
            increasing_line_color='#26a69a',
            decreasing_line_color='#ef5350',
            text=bars['timestamp_str'],
            hoverinfo='text',
        ),
        row=1, col=1
    )
    
    # Add technical indicators
    if show_ema_9:
        ema_9 = calculate_ema(bars, 9)
        fig.add_trace(
            go.Scatter(
                x=bars['x_index'],
                y=ema_9,
                mode='lines',
                name='EMA 9',
                line=dict(color='#FFA500', width=1),
            ),
            row=1, col=1
        )
    
    if show_ema_21:
        ema_21 = calculate_ema(bars, 21)
        fig.add_trace(
            go.Scatter(
                x=bars['x_index'],
                y=ema_21,
                mode='lines',
                name='EMA 21',
                line=dict(color='#00BFFF', width=1),
            ),
            row=1, col=1
        )
    
    if show_ema_50:
        ema_50 = calculate_ema(bars, 50)
        fig.add_trace(
            go.Scatter(
                x=bars['x_index'],
                y=ema_50,
                mode='lines',
                name='EMA 50',
                line=dict(color='#FF1493', width=1),
            ),
            row=1, col=1
        )
    
    if show_vwap:
        vwap = calculate_vwap(bars)
        fig.add_trace(
            go.Scatter(
                x=bars['x_index'],
                y=vwap,
                mode='lines',
                name='VWAP',
                line=dict(color='#FFD700', width=2, dash='dash'),
            ),
            row=1, col=1
        )
    
    if show_bb:
        bb_middle, bb_upper, bb_lower = calculate_bollinger_bands(bars)
        
        # Upper band
        fig.add_trace(
            go.Scatter(
                x=bars['x_index'],
                y=bb_upper,
                mode='lines',
                name='BB Upper',
                line=dict(color='#808080', width=1, dash='dot'),
                showlegend=False,
            ),
            row=1, col=1
        )
        
        # Middle band
        fig.add_trace(
            go.Scatter(
                x=bars['x_index'],
                y=bb_middle,
                mode='lines',
                name='BB Middle',
                line=dict(color='#808080', width=1),
            ),
            row=1, col=1
        )
        
        # Lower band with fill
        fig.add_trace(
            go.Scatter(
                x=bars['x_index'],
                y=bb_lower,
                mode='lines',
                name='BB Lower',
                line=dict(color='#808080', width=1, dash='dot'),
                fill='tonexty',
                fillcolor='rgba(128, 128, 128, 0.1)',
                showlegend=False,
            ),
            row=1, col=1
        )
    
    # Add volume bars
    colors = ['#ef5350' if bars['close'].iloc[i] < bars['open'].iloc[i] else '#26a69a' 
              for i in range(len(bars))]
    
    fig.add_trace(
        go.Bar(
            x=bars['x_index'],
            y=bars['volume'],
            name='Volume',
            marker_color=colors,
            showlegend=False,
            hoverinfo='y',
        ),
        row=2, col=1
    )
    
    # Add trades
    if not trades.empty:
        # Map trade times to x_index
        def find_x_index(timestamp):
            """Find closest x_index for a given timestamp."""
            idx = bars.index.get_indexer([timestamp], method='nearest')[0]
            if idx >= 0 and idx < len(bars):
                return bars['x_index'].iloc[idx]
            return None
        
        # Separate winners and losers
        winners = trades[trades['pnl'] > 0].copy()
        losers = trades[trades['pnl'] <= 0].copy()
        
        # Map times to x_index
        if not winners.empty:
            winners['entry_x'] = winners['entry_time'].apply(find_x_index)
            winners['exit_x'] = winners['exit_time'].apply(find_x_index)
            winners = winners.dropna(subset=['entry_x', 'exit_x'])
        
        if not losers.empty:
            losers['entry_x'] = losers['entry_time'].apply(find_x_index)
            losers['exit_x'] = losers['exit_time'].apply(find_x_index)
            losers = losers.dropna(subset=['entry_x', 'exit_x'])
        
        # Add entry markers for winners
        if not winners.empty:
            fig.add_trace(
                go.Scatter(
                    x=winners['entry_x'],
                    y=winners['entry_price'],
                    mode='markers',
                    name='Long Entry (Win)' if winners['direction'].iloc[0] == 'LONG' else 'Short Entry (Win)',
                    marker=dict(
                        symbol='triangle-up' if winners['direction'].iloc[0] == 'LONG' else 'triangle-down',
                        size=15,
                        color='#26a69a',
                        line=dict(width=2, color='white'),
                    ),
                    text=[f"Entry (WIN)<br>{t.strftime('%Y-%m-%d %H:%M')}<br>${p:.2f}" 
                          for t, p in zip(winners['entry_time'], winners['entry_price'])],
                    hoverinfo='text',
                ),
                row=1, col=1
            )
            
            # Add exit markers for winners
            fig.add_trace(
                go.Scatter(
                    x=winners['exit_x'],
                    y=winners['exit_price'],
                    mode='markers',
                    name='Exit (Win)',
                    marker=dict(
                        symbol='circle',
                        size=12,
                        color='#26a69a',
                        line=dict(width=2, color='white'),
                    ),
                    text=[f"Exit (WIN)<br>{t.strftime('%Y-%m-%d %H:%M')}<br>${p:.2f}" 
                          for t, p in zip(winners['exit_time'], winners['exit_price'])],
                    hoverinfo='text',
                ),
                row=1, col=1
            )
        
        # Add entry markers for losers
        if not losers.empty:
            fig.add_trace(
                go.Scatter(
                    x=losers['entry_x'],
                    y=losers['entry_price'],
                    mode='markers',
                    name='Long Entry (Loss)' if losers['direction'].iloc[0] == 'LONG' else 'Short Entry (Loss)',
                    marker=dict(
                        symbol='triangle-up' if losers['direction'].iloc[0] == 'LONG' else 'triangle-down',
                        size=15,
                        color='#ef5350',
                        line=dict(width=2, color='white'),
                    ),
                    text=[f"Entry (LOSS)<br>{t.strftime('%Y-%m-%d %H:%M')}<br>${p:.2f}" 
                          for t, p in zip(losers['entry_time'], losers['entry_price'])],
                    hoverinfo='text',
                ),
                row=1, col=1
            )
            
            # Add exit markers for losers
            fig.add_trace(
                go.Scatter(
                    x=losers['exit_x'],
                    y=losers['exit_price'],
                    mode='markers',
                    name='Exit (Loss)',
                    marker=dict(
                        symbol='circle',
                        size=12,
                        color='#ef5350',
                        line=dict(width=2, color='white'),
                    ),
                    text=[f"Exit (LOSS)<br>{t.strftime('%Y-%m-%d %H:%M')}<br>${p:.2f}" 
                          for t, p in zip(losers['exit_time'], losers['exit_price'])],
                    hoverinfo='text',
                ),
                row=1, col=1
            )
        
        # Add trade lines connecting entry to exit
        all_trades_with_x = pd.concat([winners, losers]) if not winners.empty and not losers.empty else (winners if not winners.empty else losers)
        for _, trade in all_trades_with_x.iterrows():
            color = '#26a69a' if trade['pnl'] > 0 else '#ef5350'
            
            fig.add_trace(
                go.Scatter(
                    x=[trade['entry_x'], trade['exit_x']],
                    y=[trade['entry_price'], trade['exit_price']],
                    mode='lines',
                    line=dict(color=color, width=1, dash='dot'),
                    showlegend=False,
                    hoverinfo='skip',
                ),
                row=1, col=1
            )
    
    # Create custom x-axis tick labels (show every Nth bar)
    n_ticks = min(10, len(bars))  # Max 10 labels
    tick_step = max(1, len(bars) // n_ticks)
    tickvals = list(range(0, len(bars), tick_step))
    ticktext = [bars['timestamp_str'].iloc[i] if i < len(bars) else '' for i in tickvals]
    
    # Update layout
    fig.update_layout(
        height=height,
        template='plotly_dark',
        hovermode='closest',
        xaxis_rangeslider_visible=False,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        margin=dict(l=50, r=50, t=50, b=50),
        xaxis=dict(
            tickmode='array',
            tickvals=tickvals,
            ticktext=ticktext,
            tickangle=45,
        ),
        xaxis2=dict(
            tickmode='array',
            tickvals=tickvals,
            ticktext=ticktext,
            tickangle=45,
        ),
    )
    
    # Update axes
    fig.update_xaxes(title_text="Time", row=2, col=1)
    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)
    
    return fig


def create_detailed_trade_view(
    bars: pd.DataFrame,
    trade: pd.Series,
    playbook_name: str,
) -> go.Figure:
    """
    Create a detailed view of a single trade with stop loss, targets, and MFE/MAE.
    
    Args:
        bars: OHLCV data filtered to trade duration + context
        trade: Single trade row
        playbook_name: Name of the playbook
        
    Returns:
        Plotly figure with detailed trade visualization
    """
    fig = go.Figure()
    
    # Add candlestick chart
    fig.add_trace(
        go.Candlestick(
            x=bars.index,
            open=bars['open'],
            high=bars['high'],
            low=bars['low'],
            close=bars['close'],
            name='Price',
            increasing_line_color='#26a69a',
            decreasing_line_color='#ef5350',
        )
    )
    
    # Entry marker
    direction_symbol = 'triangle-up' if trade['direction'] == 'LONG' else 'triangle-down'
    entry_color = '#26a69a' if trade['pnl'] > 0 else '#ef5350'
    
    fig.add_trace(
        go.Scatter(
            x=[trade['entry_time']],
            y=[trade['entry_price']],
            mode='markers+text',
            name='Entry',
            marker=dict(
                symbol=direction_symbol,
                size=20,
                color=entry_color,
                line=dict(width=2, color='white'),
            ),
            text=['ENTRY'],
            textposition='top center' if trade['direction'] == 'LONG' else 'bottom center',
            textfont=dict(size=10, color='white'),
        )
    )
    
    # Exit marker
    fig.add_trace(
        go.Scatter(
            x=[trade['exit_time']],
            y=[trade['exit_price']],
            mode='markers+text',
            name='Exit',
            marker=dict(
                symbol='circle',
                size=18,
                color=entry_color,
                line=dict(width=2, color='white'),
            ),
            text=['EXIT'],
            textposition='top center',
            textfont=dict(size=10, color='white'),
        )
    )
    
    # Entry price line (dashed)
    fig.add_hline(
        y=trade['entry_price'],
        line_dash="dash",
        line_color="white",
        opacity=0.5,
        annotation_text=f"Entry: {trade['entry_price']:.2f}",
        annotation_position="right",
    )
    
    # Calculate stop loss and target prices (approximation based on R-multiple)
    if 'initial_stop' in trade and not pd.isna(trade['initial_stop']):
        stop_price = trade['initial_stop']
    else:
        # Estimate stop from MAE
        risk = abs(trade['mae']) if 'mae' in trade else 0.01
        stop_price = trade['entry_price'] - risk if trade['direction'] == 'LONG' else trade['entry_price'] + risk
    
    # Stop loss line
    fig.add_hline(
        y=stop_price,
        line_dash="dot",
        line_color="#ef5350",
        opacity=0.7,
        annotation_text=f"Stop: {stop_price:.2f}",
        annotation_position="right",
    )
    
    # MFE/MAE levels if available
    if 'mfe' in trade and not pd.isna(trade['mfe']) and trade['mfe'] != 0:
        mfe_price = trade['entry_price'] + (trade['mfe'] * abs(trade['entry_price'] - stop_price))
        if trade['direction'] == 'SHORT':
            mfe_price = trade['entry_price'] - (trade['mfe'] * abs(trade['entry_price'] - stop_price))
        
        fig.add_hline(
            y=mfe_price,
            line_dash="dot",
            line_color="#26a69a",
            opacity=0.5,
            annotation_text=f"MFE: {mfe_price:.2f} ({trade['mfe']:.2f}R)",
            annotation_position="left",
        )
    
    if 'mae' in trade and not pd.isna(trade['mae']) and trade['mae'] != 0:
        mae_price = trade['entry_price'] + (trade['mae'] * abs(trade['entry_price'] - stop_price))
        if trade['direction'] == 'SHORT':
            mae_price = trade['entry_price'] - (trade['mae'] * abs(trade['entry_price'] - stop_price))
        
        fig.add_hline(
            y=mae_price,
            line_dash="dot",
            line_color="#ef5350",
            opacity=0.5,
            annotation_text=f"MAE: {mae_price:.2f} ({trade['mae']:.2f}R)",
            annotation_position="left",
        )
    
    # Add shaded region for trade duration
    fig.add_vrect(
        x0=trade['entry_time'],
        x1=trade['exit_time'],
        fillcolor=entry_color,
        opacity=0.1,
        line_width=0,
    )
    
    # Update layout
    win_loss = "WIN" if trade['pnl'] > 0 else "LOSS"
    fig.update_layout(
        title=f"{playbook_name} - {trade['direction']} {win_loss} | " +
              f"P&L: ${trade['pnl']:.2f} ({trade['r_multiple']:.2f}R) | " +
              f"Exit: {trade.get('exit_reason', 'N/A')}",
        height=600,
        template='plotly_dark',
        hovermode='x unified',
        xaxis_rangeslider_visible=False,
        showlegend=True,
        xaxis_title="Time",
        yaxis_title="Price",
    )
    
    return fig


def create_trade_metrics_table(trades_df: pd.DataFrame) -> pd.DataFrame:
    """
    Create a comprehensive trade metrics table showing all decision factors.
    
    Args:
        trades_df: DataFrame with trade data
        
    Returns:
        DataFrame formatted for display with all trade metrics
    """
    if trades_df.empty:
        return pd.DataFrame()
    
    # Create comprehensive metrics table
    metrics_data = []
    
    for idx, trade in trades_df.iterrows():
        metrics = {
            # Trade Identity
            'Trade #': idx + 1 if isinstance(idx, int) else idx,
            'Playbook': trade['playbook'],
            'Direction': trade['direction'],
            
            # Timing
            'Entry Time': trade['entry_time'].strftime('%m/%d %H:%M'),
            'Exit Time': trade['exit_time'].strftime('%m/%d %H:%M'),
            'Duration (bars)': trade.get('bars_in_trade', 'N/A'),
            
            # Prices & Execution
            'Entry Price': f"${trade['entry_price']:.2f}",
            'Exit Price': f"${trade['exit_price']:.2f}",
            'Size': f"{trade['size']} contracts",
            
            # Performance
            'P&L': f"${trade['pnl']:,.2f}",
            'R-Multiple': f"{trade['r_multiple']:.2f}R",
            'MFE': f"{trade.get('mfe', 0):.2f}R",
            'MAE': f"{trade.get('mae', 0):.2f}R",
            
            # Exit Reason
            'Exit Reason': trade.get('exit_reason', 'N/A'),
            
            # Win/Loss
            'Outcome': '✅ WIN' if trade['pnl'] > 0 else '❌ LOSS',
        }
        
        # Add metadata if available
        if 'metadata' in trade and isinstance(trade['metadata'], dict):
            metadata = trade['metadata']
            if 'regime' in metadata:
                metrics['Regime'] = metadata['regime']
            if 'signal_strength' in metadata:
                metrics['Signal Strength'] = metadata['signal_strength']
        
        metrics_data.append(metrics)
    
    return pd.DataFrame(metrics_data)


def page_chart_analysis(data: dict):
    """
    Main chart analysis page with TradingView-style visualization.
    
    Args:
        data: Dictionary containing run data including trades and metrics
    """
    st.title("📈 Trade Chart Analysis")
    st.markdown("*Professional TradingView-style visualization of all trades*")
    
    # Get run info
    run_id = data['run_id']
    trades_df = data['trades']
    
    if trades_df.empty:
        st.warning("No trades found in this run.")
        return
    
    # Load OHLCV data
    run_path = Path(f"runs/{run_id}")
    
    # Try to find price data files
    parquet_files = list(run_path.glob("*_bars_1m.parquet"))
    if not parquet_files:
        st.error("No price data found for this run. Charts cannot be displayed.")
        st.info("💡 Price data should be saved as `{symbol}_bars_1m.parquet` in the run directory.")
        return
    
    # Load price data
    bars_df = pd.read_parquet(parquet_files[0])
    
    # Ensure timestamp index
    if 'timestamp_utc' in bars_df.columns:
        bars_df.index = pd.to_datetime(bars_df['timestamp_utc'])
    elif not isinstance(bars_df.index, pd.DatetimeIndex):
        st.error("Price data does not have a valid timestamp index.")
        return
    
    bars_df = bars_df.sort_index()
    
    st.success(f"✅ Loaded {len(bars_df):,} bars from {bars_df.index[0]} to {bars_df.index[-1]}")
    
    # Sidebar filters
    st.sidebar.markdown("## 🎛️ Chart Settings")
    
    # Timeframe selector
    st.sidebar.markdown("### 📊 Timeframe")
    timeframe = st.sidebar.selectbox(
        "Candle Period",
        ['1m', '5m', '15m', '30m', '1h'],
        index=0,
        help="Select candlestick timeframe"
    )
    
    # Technical indicators
    st.sidebar.markdown("### 📈 Technical Indicators")
    show_ema_9 = st.sidebar.checkbox("EMA 9", value=False, help="9-period Exponential Moving Average")
    show_ema_21 = st.sidebar.checkbox("EMA 21", value=False, help="21-period EMA (fast trend)")
    show_ema_50 = st.sidebar.checkbox("EMA 50", value=False, help="50-period EMA (slow trend)")
    show_vwap = st.sidebar.checkbox("VWAP", value=True, help="Volume Weighted Average Price")
    show_bb = st.sidebar.checkbox("Bollinger Bands", value=False, help="20-period BB (2σ)")
    
    # Filters
    st.sidebar.markdown("### 🎯 Trade Filters")
    
    # Playbook filter
    playbooks = ['All'] + sorted(trades_df['playbook'].unique().tolist())
    selected_playbook = st.sidebar.selectbox("Playbook", playbooks)
    
    # Win/Loss filter
    outcome_filter = st.sidebar.radio(
        "Trade Outcome",
        ["All", "Winners Only", "Losers Only"]
    )
    
    # Date range filter
    min_date = trades_df['entry_time'].min().date()
    max_date = trades_df['exit_time'].max().date()
    
    date_range = st.sidebar.date_input(
        "Date Range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    
    # Apply filters
    filtered_trades = trades_df.copy()
    
    if selected_playbook != 'All':
        filtered_trades = filtered_trades[filtered_trades['playbook'] == selected_playbook]
    
    if outcome_filter == "Winners Only":
        filtered_trades = filtered_trades[filtered_trades['pnl'] > 0]
    elif outcome_filter == "Losers Only":
        filtered_trades = filtered_trades[filtered_trades['pnl'] <= 0]
    
    if len(date_range) == 2:
        start_date, end_date = date_range
        filtered_trades = filtered_trades[
            (filtered_trades['entry_time'].dt.date >= start_date) &
            (filtered_trades['entry_time'].dt.date <= end_date)
        ]
    
    st.sidebar.markdown(f"**{len(filtered_trades)} trades** match filters")
    
    # Filter bars to date range
    if len(date_range) == 2:
        # Make timestamps timezone-aware to match bars_df index
        start_datetime = pd.Timestamp(start_date, tz='UTC')
        end_datetime = pd.Timestamp(end_date, tz='UTC') + pd.Timedelta(days=1)
        filtered_bars = bars_df[(bars_df.index >= start_datetime) & (bars_df.index < end_datetime)]
    else:
        filtered_bars = bars_df
    
    # Resample bars to selected timeframe
    if timeframe != '1m':
        with st.spinner(f'Resampling to {timeframe}...'):
            filtered_bars = resample_bars(filtered_bars, timeframe)
        st.info(f"📊 Chart resampled to {timeframe} candles ({len(filtered_bars):,} bars)")
    
    # Main chart with all filtered trades
    st.markdown("---")
    st.markdown("### 📊 Overview Chart - All Trades")
    
    if not filtered_trades.empty:
        chart_title = f"{selected_playbook} Trades ({timeframe})" if selected_playbook != 'All' else f"All Playbooks ({timeframe})"
        fig = create_tradingview_chart(
            bars=filtered_bars,
            trades=filtered_trades,
            title=chart_title,
            height=800,
            show_ema_9=show_ema_9,
            show_ema_21=show_ema_21,
            show_ema_50=show_ema_50,
            show_vwap=show_vwap,
            show_bb=show_bb,
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # Trade statistics for filtered trades
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("Total Trades", len(filtered_trades))
        
        with col2:
            win_rate = (filtered_trades['pnl'] > 0).sum() / len(filtered_trades) * 100
            st.metric("Win Rate", f"{win_rate:.1f}%")
        
        with col3:
            total_pnl = filtered_trades['pnl'].sum()
            st.metric("Total P&L", f"${total_pnl:,.0f}")
        
        with col4:
            avg_r = filtered_trades['r_multiple'].mean()
            st.metric("Avg R", f"{avg_r:.2f}R")
        
        with col5:
            profit_factor = abs(filtered_trades[filtered_trades['pnl'] > 0]['pnl'].sum() / 
                               filtered_trades[filtered_trades['pnl'] < 0]['pnl'].sum()) if (filtered_trades['pnl'] < 0).any() else float('inf')
            st.metric("Profit Factor", f"{profit_factor:.2f}" if profit_factor != float('inf') else "∞")
        
        # Win Rate Heatmap
        st.markdown("---")
        st.markdown("### 🔥 Win Rate Heatmap - Time & Price Analysis")
        st.markdown("*Shows win rate distribution across time of day and price levels*")
        
        if len(filtered_trades) >= 5:  # Need minimum trades for meaningful heatmap
            heatmap_fig = create_win_rate_heatmap(filtered_bars, filtered_trades, price_bins=30)
            if heatmap_fig is not None:
                st.plotly_chart(heatmap_fig, use_container_width=True)
                
                # Heatmap insights
                st.markdown("**📊 Heatmap Insights:**")
                col1, col2 = st.columns(2)
                
                with col1:
                    # Best hour
                    hourly_stats = filtered_trades.groupby(filtered_trades['entry_time'].dt.hour).agg({
                        'pnl': ['count', lambda x: (x > 0).sum() / len(x)]
                    })
                    if not hourly_stats.empty:
                        best_hour = hourly_stats[('pnl', '<lambda>')].idxmax()
                        best_hour_wr = hourly_stats[('pnl', '<lambda>')].max() * 100
                        st.info(f"🕐 **Best Hour:** {best_hour}:00 ({best_hour_wr:.1f}% win rate)")
                
                with col2:
                    # Best price zone
                    price_quartiles = filtered_trades['entry_price'].quantile([0.25, 0.5, 0.75])
                    low_zone = filtered_trades[filtered_trades['entry_price'] < price_quartiles[0.25]]
                    mid_zone = filtered_trades[(filtered_trades['entry_price'] >= price_quartiles[0.25]) & 
                                              (filtered_trades['entry_price'] < price_quartiles[0.75])]
                    high_zone = filtered_trades[filtered_trades['entry_price'] >= price_quartiles[0.75]]
                    
                    zones = {
                        'Low': (low_zone['pnl'] > 0).mean() * 100 if len(low_zone) > 0 else 0,
                        'Mid': (mid_zone['pnl'] > 0).mean() * 100 if len(mid_zone) > 0 else 0,
                        'High': (high_zone['pnl'] > 0).mean() * 100 if len(high_zone) > 0 else 0,
                    }
                    best_zone = max(zones, key=zones.get)
                    st.info(f"📍 **Best Price Zone:** {best_zone} ({zones[best_zone]:.1f}% win rate)")
        else:
            st.info(f"Need at least 5 trades to display heatmap (currently {len(filtered_trades)} trades)")
        
        # Comprehensive Trade Metrics Table
        st.markdown("---")
        st.markdown("### 📋 Comprehensive Trade Metrics")
        st.markdown("*Complete decision factors and outcomes for every trade*")
        
        # Create and display the metrics table
        metrics_table = create_trade_metrics_table(filtered_trades)
        
        if not metrics_table.empty:
            # Add color coding to the outcome column
            def highlight_outcome(val):
                if '✅ WIN' in str(val):
                    return 'background-color: rgba(38, 166, 154, 0.2)'
                elif '❌ LOSS' in str(val):
                    return 'background-color: rgba(239, 83, 80, 0.2)'
                return ''
            
            # Style the dataframe
            styled_table = metrics_table.style.applymap(
                highlight_outcome,
                subset=['Outcome'] if 'Outcome' in metrics_table.columns else []
            )
            
            # Display with filtering and sorting
            st.dataframe(
                styled_table,
                use_container_width=True,
                height=400,
            )
            
            # Download button
            csv = metrics_table.to_csv(index=False)
            st.download_button(
                label="📥 Download Trade Metrics CSV",
                data=csv,
                file_name=f"trade_metrics_{data['run_id']}.csv",
                mime="text/csv",
            )
            
            # Quick stats from table
            col1, col2, col3 = st.columns(3)
            
            with col1:
                avg_duration = metrics_table[metrics_table['Duration (bars)'] != 'N/A']['Duration (bars)'].astype(float).mean()
                st.metric("Avg Duration", f"{avg_duration:.0f} bars" if not pd.isna(avg_duration) else "N/A")
            
            with col2:
                stop_exits = len(metrics_table[metrics_table['Exit Reason'] == 'STOP'])
                st.metric("Stop Exits", f"{stop_exits} ({stop_exits/len(metrics_table)*100:.1f}%)")
            
            with col3:
                salvage_exits = len(metrics_table[metrics_table['Exit Reason'] == 'SALVAGE'])
                st.metric("Salvage Exits", f"{salvage_exits} ({salvage_exits/len(metrics_table)*100:.1f}%)")
        
        # Detailed trade viewer
        st.markdown("---")
        st.markdown("### 🔍 Detailed Trade View")
        st.markdown("*Select a trade to see detailed entry, exit, stops, and MFE/MAE levels*")
        
        # Create trade selector
        trade_options = []
        for idx, trade in filtered_trades.iterrows():
            win_loss = "WIN" if trade['pnl'] > 0 else "LOSS"
            trade_label = (
                f"{idx}: {trade['playbook']} | {trade['direction']} {win_loss} | "
                f"{trade['entry_time'].strftime('%Y-%m-%d %H:%M')} | "
                f"${trade['pnl']:.0f} ({trade['r_multiple']:.2f}R)"
            )
            trade_options.append((idx, trade_label))
        
        selected_trade_idx = st.selectbox(
            "Select Trade",
            options=[t[0] for t in trade_options],
            format_func=lambda x: next(t[1] for t in trade_options if t[0] == x),
        )
        
        if selected_trade_idx is not None:
            trade = filtered_trades.loc[selected_trade_idx]
            
            # Get bars for this trade with context
            context_minutes = 120  # 2 hours before and after
            trade_start = trade['entry_time'] - pd.Timedelta(minutes=context_minutes)
            trade_end = trade['exit_time'] + pd.Timedelta(minutes=context_minutes)
            
            trade_bars = bars_df[(bars_df.index >= trade_start) & (bars_df.index <= trade_end)]
            
            if not trade_bars.empty:
                # Create detailed trade chart
                fig_detail = create_detailed_trade_view(
                    bars=trade_bars,
                    trade=trade,
                    playbook_name=trade['playbook'],
                )
                st.plotly_chart(fig_detail, use_container_width=True)
                
                # Trade details table
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("#### 📋 Trade Details")
                    details_data = {
                        "Playbook": trade['playbook'],
                        "Direction": trade['direction'],
                        "Entry Time": trade['entry_time'].strftime('%Y-%m-%d %H:%M:%S'),
                        "Exit Time": trade['exit_time'].strftime('%Y-%m-%d %H:%M:%S'),
                        "Duration": f"{trade.get('bars_in_trade', 'N/A')} bars",
                        "Exit Reason": trade.get('exit_reason', 'N/A'),
                    }
                    for key, value in details_data.items():
                        st.text(f"{key}: {value}")
                
                with col2:
                    st.markdown("#### 💰 Performance")
                    perf_data = {
                        "Entry Price": f"${trade['entry_price']:.2f}",
                        "Exit Price": f"${trade['exit_price']:.2f}",
                        "Size": f"{trade['size']} contracts",
                        "P&L": f"${trade['pnl']:.2f}",
                        "R-Multiple": f"{trade['r_multiple']:.2f}R",
                        "MFE": f"{trade.get('mfe', 0):.2f}R",
                        "MAE": f"{trade.get('mae', 0):.2f}R",
                    }
                    for key, value in perf_data.items():
                        st.text(f"{key}: {value}")
            else:
                st.warning("No price data available for this trade's time range.")
    
    else:
        st.info("No trades match the selected filters.")

