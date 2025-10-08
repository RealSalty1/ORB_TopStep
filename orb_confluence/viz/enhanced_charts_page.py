"""Enhanced charts page with ORB and trade overlays."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
from pathlib import Path


def page_charts_enhanced(futures_data, load_runs_func, get_chart_config_func):
    """
    Enhanced page for viewing full futures price charts with ORB and trade overlays.
    
    Args:
        futures_data: Dict of futures data loaded from cache
        load_runs_func: Function to load available backtest runs
        get_chart_config_func: Function to get chart configuration
    """
    st.title("📈 Futures Price Charts")
    
    if not futures_data:
        st.warning("⚠️ No cached futures data found!")
        st.info("Run the data fetch script first:")
        st.code("python scripts/fetch_futures_data.py", language="bash")
        return
    
    # Asset selector and chart options
    col1, col2, col3 = st.columns([2, 2, 3])
    
    with col1:
        symbols = sorted(futures_data.keys())
        selected_symbol = st.selectbox(
            "📊 Symbol",
            symbols,
            format_func=lambda x: f"{x} - {futures_data[x]['display_name']}"
        )
    
    # Load available runs for trade/ORB data
    runs = load_runs_func()
    multi_instrument_runs = [r for r in runs if r.startswith('multi_instrument_')]
    
    with col2:
        if multi_instrument_runs:
            selected_run = st.selectbox(
                "📁 Backtest Run (optional)",
                ["None"] + multi_instrument_runs,
                help="Select a backtest run to overlay ORB zones and trades"
            )
        else:
            selected_run = "None"
            st.info("No multi-instrument runs found")
    
    # Chart display options
    with col3:
        st.markdown("**Chart Options:**")
        col_opt1, col_opt2, col_opt3 = st.columns(3)
        with col_opt1:
            show_volume = st.checkbox("📊 Volume", value=True)
            show_orb = st.checkbox("📐 ORB Zones", value=True)
        with col_opt2:
            show_entries = st.checkbox("🎯 Entries", value=True)
            show_exits = st.checkbox("🚪 Exits", value=True)
        with col_opt3:
            show_stops = st.checkbox("🛑 Stops", value=True)
            show_targets = st.checkbox("🎯 Targets", value=True)
    
    if not selected_symbol:
        return
        
    contract_info = futures_data[selected_symbol]
    df = contract_info['data']
    
    # Load backtest data if selected
    trades_for_symbol = []
    orb_zones = []
    
    if selected_run != "None":
        run_path = Path("runs") / selected_run
        trades_file = run_path / "all_trades.json"
        
        if trades_file.exists():
            with open(trades_file, 'r') as f:
                all_trades = json.load(f)
                
            # Filter trades for this symbol
            trades_for_symbol = [t for t in all_trades if t.get('instrument') == selected_symbol]
            
            # Extract ORB zones by date (from all trades, will filter by date later)
            orb_by_date = {}
            for trade in trades_for_symbol:
                date = trade.get('date')
                or_metrics = trade.get('or_metrics', {})
                if date and or_metrics and date not in orb_by_date:
                    orb_by_date[date] = {
                        'start_ts': pd.to_datetime(or_metrics.get('start_ts')),
                        'end_ts': pd.to_datetime(or_metrics.get('end_ts')),
                        'high': or_metrics.get('high'),
                        'low': or_metrics.get('low'),
                    }
            
            orb_zones = list(orb_by_date.values())
    
    # Display contract info
    st.markdown(f"""
    **{contract_info['display_name']}** ({contract_info['yahoo_symbol']})  
    📊 {contract_info['bar_count']:,} bars | ⏱️ {contract_info['interval']} intervals | 
    📅 {df['timestamp'].min().strftime('%Y-%m-%d')} to {df['timestamp'].max().strftime('%Y-%m-%d')}
    """)
    
    if trades_for_symbol:
        st.info(f"📌 Found {len(trades_for_symbol)} trades and {len(orb_zones)} ORB zones for {selected_symbol}")
    
    st.markdown("---")
    
    # Date range selector
    st.markdown("### 📅 Date Range Filter")
    col_date1, col_date2, col_date3 = st.columns([2, 2, 3])
    
    # Get unique trading dates
    df['date'] = pd.to_datetime(df['timestamp']).dt.date
    unique_dates = sorted(df['date'].unique())
    
    with col_date1:
        # Default to last 5 days
        default_start_idx = max(0, len(unique_dates) - 5)
        start_date = st.selectbox(
            "Start Date",
            unique_dates,
            index=default_start_idx,
            format_func=lambda x: x.strftime('%Y-%m-%d')
        )
    
    with col_date2:
        end_date = st.selectbox(
            "End Date", 
            unique_dates,
            index=len(unique_dates) - 1,
            format_func=lambda x: x.strftime('%Y-%m-%d')
        )
    
    with col_date3:
        quick_ranges = st.selectbox(
            "Quick Select",
            ["Last 1 Day", "Last 5 Days", "Last 10 Days", "1 Month", "3 Months", "6 Months", "1 Year", "2025 YTD", "All Data (5 Years)"],
            index=1
        )
        
        # Apply quick range
        end_date = unique_dates[-1]
        if quick_ranges == "Last 1 Day":
            start_date = unique_dates[-1]
        elif quick_ranges == "Last 5 Days":
            start_date = unique_dates[max(0, len(unique_dates) - 5)]
        elif quick_ranges == "Last 10 Days":
            start_date = unique_dates[max(0, len(unique_dates) - 10)]
        elif quick_ranges == "1 Month":
            # Approx 20 trading days
            start_date = unique_dates[max(0, len(unique_dates) - 20)]
        elif quick_ranges == "3 Months":
            # Approx 60 trading days
            start_date = unique_dates[max(0, len(unique_dates) - 60)]
        elif quick_ranges == "6 Months":
            # Approx 120 trading days
            start_date = unique_dates[max(0, len(unique_dates) - 120)]
        elif quick_ranges == "1 Year":
            # Approx 252 trading days
            start_date = unique_dates[max(0, len(unique_dates) - 252)]
        elif quick_ranges == "2025 YTD":
            # From Jan 1, 2025
            ytd_dates = [d for d in unique_dates if d >= pd.Timestamp('2025-01-01').date()]
            start_date = ytd_dates[0] if ytd_dates else unique_dates[0]
        else:  # All Data (5 Years)
            start_date = unique_dates[0]
    
    # Filter dataframe by date range
    df_filtered = df[(df['date'] >= start_date) & (df['date'] <= end_date)].copy()
    
    st.markdown("---")
    
    # Display stats for filtered range
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("Current Price", f"${df_filtered.iloc[-1]['close']:.2f}")
    
    with col2:
        price_change = df_filtered.iloc[-1]['close'] - df_filtered.iloc[0]['close']
        price_change_pct = (price_change / df_filtered.iloc[0]['close']) * 100
        st.metric("Period Change", f"${price_change:.2f}", f"{price_change_pct:+.2f}%")
    
    with col3:
        st.metric("Period High", f"${df_filtered['high'].max():.2f}")
    
    with col4:
        st.metric("Period Low", f"${df_filtered['low'].min():.2f}")
    
    with col5:
        avg_volume = df_filtered['volume'].mean()
        st.metric("Avg Volume", f"{avg_volume:,.0f}")
    
    st.markdown("---")
    
    # Filter trades and ORB zones to the selected date range
    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date) + pd.Timedelta(days=1)
    
    trades_filtered = [
        t for t in trades_for_symbol
        if start_date <= pd.to_datetime(t.get('date')).date() <= end_date
    ]
    
    orb_zones_filtered = [
        orb for orb in orb_zones
        if start_ts <= orb['start_ts'] < end_ts
    ]
    
    if trades_filtered:
        st.success(f"✅ Showing {len(trades_filtered)} trades in selected date range")
    
    # Create subplots: main chart + volume
    row_heights = [0.7, 0.3] if show_volume else [1.0]
    subplot_titles = [f"{contract_info['display_name']} - Price ({start_date} to {end_date})", "Volume"] if show_volume else [f"{contract_info['display_name']} - Price ({start_date} to {end_date})"]
    
    fig = make_subplots(
        rows=2 if show_volume else 1,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=row_heights,
        subplot_titles=subplot_titles
    )
    
    # Add candlesticks to main chart (using filtered data)
    fig.add_trace(go.Candlestick(
        x=df_filtered['timestamp'],
        open=df_filtered['open'],
        high=df_filtered['high'],
        low=df_filtered['low'],
        close=df_filtered['close'],
        name=selected_symbol,
        increasing_line_color='#26a69a',
        decreasing_line_color='#ef5350',
        increasing_fillcolor='#26a69a',
        decreasing_fillcolor='#ef5350',
    ), row=1, col=1)
    
    # Add ORB zones if enabled (using filtered zones)
    if show_orb and orb_zones_filtered:
        for i, orb in enumerate(orb_zones_filtered):
            # ORB rectangle (shaded zone)
            fig.add_shape(
                type="rect",
                x0=orb['start_ts'],
                x1=orb['end_ts'],
                y0=orb['low'],
                y1=orb['high'],
                fillcolor="rgba(100, 149, 237, 0.2)",  # Cornflower blue
                line=dict(color="rgba(100, 149, 237, 0.5)", width=1),
                name=f"ORB {i+1}",
                row=1,
                col=1
            )
            
            # ORB high line (extends to end of day)
            orb_date = orb['start_ts'].date()
            next_day = pd.Timestamp(orb_date) + pd.Timedelta(days=1)
            end_of_day = min(next_day, df['timestamp'].max())
            
            fig.add_trace(go.Scatter(
                x=[orb['end_ts'], end_of_day],
                y=[orb['high'], orb['high']],
                mode='lines',
                line=dict(color='rgba(100, 149, 237, 0.8)', width=1, dash='dot'),
                name=f"ORB High" if i == 0 else "",
                showlegend=(i == 0),
                legendgroup="orb",
                hovertemplate=f"ORB High: ${orb['high']:.2f}<extra></extra>",
            ), row=1, col=1)
            
            # ORB low line
            fig.add_trace(go.Scatter(
                x=[orb['end_ts'], end_of_day],
                y=[orb['low'], orb['low']],
                mode='lines',
                line=dict(color='rgba(100, 149, 237, 0.8)', width=1, dash='dot'),
                name=f"ORB Low" if i == 0 else "",
                showlegend=(i == 0),
                legendgroup="orb",
                hovertemplate=f"ORB Low: ${orb['low']:.2f}<extra></extra>",
            ), row=1, col=1)
    
    # Add trade entries (using filtered trades)
    if show_entries and trades_filtered:
        entry_times = []
        entry_prices = []
        entry_colors = []
        entry_symbols = []
        entry_texts = []
        
        for trade in trades_filtered:
            breakout = trade.get('breakout_context', {})
            risk = trade.get('risk_metrics', {})
            entry_ts = pd.to_datetime(breakout.get('breakout_ts'))
            entry_price = risk.get('entry_price', 0)
            direction = breakout.get('direction', 'UNKNOWN')
            
            if entry_ts and entry_price:
                entry_times.append(entry_ts)
                entry_prices.append(entry_price)
                
                if direction == 'LONG':
                    entry_colors.append('#00ff00')  # Bright green
                    entry_symbols.append('triangle-up')
                    entry_texts.append(f"LONG Entry<br>${entry_price:.2f}")
                else:
                    entry_colors.append('#ff0000')  # Bright red
                    entry_symbols.append('triangle-down')
                    entry_texts.append(f"SHORT Entry<br>${entry_price:.2f}")
        
        if entry_times:
            fig.add_trace(go.Scatter(
                x=entry_times,
                y=entry_prices,
                mode='markers',
                marker=dict(
                    size=15,
                    color=entry_colors,
                    symbol=entry_symbols,
                    line=dict(width=2, color='white')
                ),
                name='Entries',
                text=entry_texts,
                hovertemplate='%{text}<extra></extra>',
                showlegend=True,
            ), row=1, col=1)
    
    # Add trade exits
    if show_exits and trades_for_symbol:
        exit_times = []
        exit_prices = []
        exit_texts = []
        
        for trade in trades_filtered:
            outcome = trade.get('outcome', {})
            exit_ts = pd.to_datetime(outcome.get('exit_ts'))
            exit_price = outcome.get('exit_price', 0)
            exit_reason = outcome.get('exit_reason', 'unknown')
            realized_r = outcome.get('realized_r_multiple', 0)
            
            if exit_ts and exit_price:
                exit_times.append(exit_ts)
                exit_prices.append(exit_price)
                exit_texts.append(f"EXIT ({exit_reason})<br>${exit_price:.2f}<br>{realized_r:.2f}R")
        
        if exit_times:
            fig.add_trace(go.Scatter(
                x=exit_times,
                y=exit_prices,
                mode='markers',
                marker=dict(
                    size=12,
                    color='yellow',
                    symbol='x',
                    line=dict(width=2, color='black')
                ),
                name='Exits',
                text=exit_texts,
                hovertemplate='%{text}<extra></extra>',
                showlegend=True,
            ), row=1, col=1)
    
    # Add stops and targets
    if (show_stops or show_targets) and trades_for_symbol:
        for trade in trades_filtered:
            breakout = trade.get('breakout_context', {})
            risk = trade.get('risk_metrics', {})
            outcome = trade.get('outcome', {})
            
            entry_ts = pd.to_datetime(breakout.get('breakout_ts'))
            exit_ts = pd.to_datetime(outcome.get('exit_ts'))
            
            if not entry_ts or not exit_ts:
                continue
            
            # Stop loss line
            if show_stops:
                stop_price = risk.get('initial_stop_price', 0)
                if stop_price:
                    fig.add_trace(go.Scatter(
                        x=[entry_ts, exit_ts],
                        y=[stop_price, stop_price],
                        mode='lines',
                        line=dict(color='red', width=1, dash='dash'),
                        name='Stop Loss',
                        showlegend=False,
                        hovertemplate=f"Stop: ${stop_price:.2f}<extra></extra>",
                    ), row=1, col=1)
            
            # Target lines
            if show_targets:
                targets = risk.get('targets', [])
                target_colors = ['lime', '#32cd32', '#90ee90']  # Different shades of green
                
                for idx, target in enumerate(targets[:3]):  # Show up to 3 targets
                    # The 'price' field stores the R-multiple, 'r_multiple' stores the actual price
                    r_mult = target.get('price', 0)  # This is actually the R-multiple
                    target_price = target.get('r_multiple', 0)  # This is the actual price
                    
                    if target_price and target_price > 0:
                        fig.add_trace(go.Scatter(
                            x=[entry_ts, exit_ts],
                            y=[target_price, target_price],
                            mode='lines',
                            line=dict(
                                color=target_colors[idx] if idx < len(target_colors) else '#90ee90',
                                width=1,
                                dash='dot'
                            ),
                            name=f'Target {idx+1}' if idx == 0 else '',
                            showlegend=(idx == 0),
                            legendgroup='targets',
                            hovertemplate=f"T{idx+1}: ${target_price:.2f} ({r_mult:.1f}R)<extra></extra>",
                        ), row=1, col=1)
    
    # Add volume bars if enabled
    if show_volume:
        colors = ['#26a69a' if df_filtered.iloc[i]['close'] >= df_filtered.iloc[i]['open'] else '#ef5350' 
                  for i in range(len(df_filtered))]
        
        fig.add_trace(go.Bar(
            x=df_filtered['timestamp'],
            y=df_filtered['volume'],
            name='Volume',
            marker_color=colors,
            showlegend=False,
        ), row=2, col=1)
    
    # Update layout
    chart_config = get_chart_config_func()
    
    fig.update_layout(
        height=1100 if show_volume else 900,
        template="plotly_dark",
        hovermode='x unified',
        showlegend=True,
        legend=dict(
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01,
            bgcolor='rgba(0,0,0,0.5)'
        ),
        margin=dict(l=50, r=50, t=50, b=50)
    )
    
    # Update x-axes
    rangebreaks = [
        dict(bounds=["sat", "mon"], pattern="day of week"),
        dict(bounds=[21, 22], pattern="hour"),
    ]
    
    fig.update_xaxes(
        type="date",
        showgrid=True,
        gridcolor='#2a2a2a',
        rangebreaks=rangebreaks,
        row=1, col=1
    )
    
    if show_volume:
        fig.update_xaxes(
            type="date",
            showgrid=True,
            gridcolor='#2a2a2a',
            rangebreaks=rangebreaks,
            row=2, col=1
        )
    
    # Update y-axes
    fig.update_yaxes(
        showgrid=True,
        gridcolor='#2a2a2a',
        side='right',
        row=1, col=1
    )
    
    if show_volume:
        fig.update_yaxes(
            showgrid=True,
            gridcolor='#2a2a2a',
            side='right',
            row=2, col=1
        )
    
    # Add range slider to bottom subplot
    if show_volume:
        fig.update_xaxes(rangeslider=dict(visible=True), row=2, col=1)
    else:
        fig.update_xaxes(rangeslider=dict(visible=True), row=1, col=1)
    
    st.plotly_chart(fig, use_container_width=True, config=chart_config)
    
    # Data table (sample) - using filtered data
    with st.expander("📊 View Data Table (Last 100 bars)"):
        display_df = df_filtered.tail(100)[['timestamp', 'open', 'high', 'low', 'close', 'volume']].copy()
        display_df['timestamp'] = display_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
        st.dataframe(display_df, use_container_width=True, hide_index=True)
