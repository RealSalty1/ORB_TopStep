"""Multi-instrument specific dashboard pages."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import json
from pathlib import Path


def load_multi_instrument_data(run_id):
    """Load multi-instrument backtest data."""
    run_path = Path("runs") / run_id
    
    # Check if this is a multi-instrument run
    summary_file = run_path / "summary.json"
    if not summary_file.exists():
        return None
    
    try:
        with open(summary_file, 'r') as f:
            summary = json.load(f)
        
        # Load all trades
        trades_file = run_path / "all_trades.json"
        if not trades_file.exists():
            return None
            
        with open(trades_file, 'r') as f:
            trades = json.load(f)
        
        if not trades:
            return None
        
        # Check if this is a multi-instrument run by looking for instrument field
        if 'instrument' not in trades[0]:
            return None
        
        # Compute per-instrument stats from trades
        per_instrument = {}
        for trade in trades:
            instrument = trade.get('instrument', 'UNKNOWN')
            if instrument not in per_instrument:
                per_instrument[instrument] = {
                    'trades': [],
                    'total_trades': 0,
                    'winning_trades': 0,
                    'losing_trades': 0,
                    'total_r': 0.0,
                    'total_pnl': 0.0,
                }
            
            outcome = trade.get('outcome', {})
            realized_r = outcome.get('realized_r', 0)
            realized_pnl = outcome.get('realized_dollars', 0)
            
            per_instrument[instrument]['trades'].append(trade)
            per_instrument[instrument]['total_trades'] += 1
            per_instrument[instrument]['total_r'] += realized_r
            per_instrument[instrument]['total_pnl'] += realized_pnl
            
            if realized_r > 0:
                per_instrument[instrument]['winning_trades'] += 1
            elif realized_r < 0:
                per_instrument[instrument]['losing_trades'] += 1
        
        # Calculate derived stats
        for instrument in per_instrument:
            stats = per_instrument[instrument]
            stats['win_rate'] = stats['winning_trades'] / stats['total_trades'] if stats['total_trades'] > 0 else 0
            stats['expectancy'] = stats['total_r'] / stats['total_trades'] if stats['total_trades'] > 0 else 0
        
        return {
            'summary': summary,
            'trades': trades,
            'per_instrument': per_instrument
        }
    except Exception as e:
        st.error(f"Error loading multi-instrument data: {e}")
        return None


def page_multi_instrument_overview(run_id):
    """Multi-instrument performance overview page."""
    st.title("🌐 Multi-Instrument Overview")
    
    data = load_multi_instrument_data(run_id)
    
    if data is None:
        st.warning("This backtest does not contain multi-instrument data.")
        st.markdown("""
        To view multi-instrument analysis, run a backtest with:
        ```bash
        python scripts/run_multi_instrument_backtest.py --instruments ES NQ CL GC 6E
        ```
        """)
        return
    
    summary = data['summary']
    per_instrument = data['per_instrument']
    
    # Overall stats
    st.markdown("## 📊 Portfolio Performance")
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("Total Trades", summary.get('total_trades', 0))
    
    with col2:
        total_pnl = summary.get('total_dollars', 0)
        st.metric("Total P&L", f"${total_pnl:,.2f}", 
                 delta=f"{summary.get('profit_target_pct', 0)*100:.2f}%")
    
    with col3:
        win_rate = summary.get('win_rate', 0)
        st.metric("Win Rate", f"{win_rate*100:.1f}%")
    
    with col4:
        avg_r = summary.get('expectancy', 0)
        st.metric("Expectancy", f"{avg_r:.2f}R")
    
    with col5:
        governance = summary.get('governance_status', {})
        lockout = governance.get('lockout_active', False)
        st.metric("Lockout Status", 
                 "🔒 ACTIVE" if lockout else "✅ CLEAR",
                 delta=f"{governance.get('consecutive_losses', 0)} losses" if lockout else None)
    
    st.markdown("---")
    
    # Per-instrument comparison
    st.markdown("## 📈 Per-Instrument Performance")
    
    # Create comparison DataFrame
    comparison_data = []
    for symbol, stats in per_instrument.items():
        # Calculate max win/loss from trades
        trades_list = stats.get('trades', [])
        r_multiples = [t.get('outcome', {}).get('realized_r', 0) for t in trades_list]
        max_win = max(r_multiples) if r_multiples else 0
        max_loss = min(r_multiples) if r_multiples else 0
        
        comparison_data.append({
            'Instrument': symbol,
            'Trades': stats.get('total_trades', 0),
            'Win Rate': stats.get('win_rate', 0),
            'Avg R': stats.get('expectancy', 0),  # expectancy is avg R
            'Total R': stats.get('total_r', 0),
            'Max Win (R)': max_win,
            'Max Loss (R)': max_loss,
            'Expectancy': stats.get('expectancy', 0)
        })
    
    df_comparison = pd.DataFrame(comparison_data)
    
    # Sort by Total R
    df_comparison = df_comparison.sort_values('Total R', ascending=False)
    
    # Display metrics by instrument
    cols = st.columns(len(df_comparison))
    for idx, (_, row) in enumerate(df_comparison.iterrows()):
        with cols[idx]:
            st.markdown(f"### {row['Instrument']}")
            st.metric("Trades", int(row['Trades']))
            st.metric("Win Rate", f"{row['Win Rate']*100:.1f}%")
            st.metric("Total R", f"{row['Total R']:.2f}R")
            st.metric("Expectancy", f"{row['Expectancy']:.2f}R")
    
    st.markdown("---")
    
    # Detailed comparison table
    st.markdown("### 📋 Detailed Comparison")
    
    # Keep numeric version for charts BEFORE formatting
    df_comparison_numeric = df_comparison.copy()
    
    # Format the DataFrame for display
    display_df = df_comparison.copy()
    display_df['Win Rate'] = display_df['Win Rate'].apply(lambda x: f"{x*100:.1f}%")
    display_df['Avg R'] = display_df['Avg R'].apply(lambda x: f"{x:.2f}R")
    display_df['Total R'] = display_df['Total R'].apply(lambda x: f"{x:.2f}R")
    display_df['Max Win (R)'] = display_df['Max Win (R)'].apply(lambda x: f"{x:.2f}R")
    display_df['Max Loss (R)'] = display_df['Max Loss (R)'].apply(lambda x: f"{x:.2f}R")
    display_df['Expectancy'] = display_df['Expectancy'].apply(lambda x: f"{x:.2f}R")
    
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    
    st.markdown("---")
    
    # Equity Curve Chart
    st.markdown("### 📈 Portfolio Equity Curve")
    
    # Build equity curve from all trades
    trades_with_time = []
    for trade in data['trades']:
        outcome = trade.get('outcome', {})
        trades_with_time.append({
            'timestamp': outcome.get('exit_ts', ''),
            'instrument': trade.get('instrument', 'UNKNOWN'),
            'realized_r': outcome.get('realized_r', 0),
            'realized_pnl': outcome.get('realized_dollars', 0)
        })
    
    # Sort by timestamp
    df_equity = pd.DataFrame(trades_with_time)
    df_equity = df_equity.sort_values('timestamp')
    
    # Calculate cumulative values
    df_equity['cumulative_r'] = df_equity['realized_r'].cumsum()
    df_equity['cumulative_pnl'] = df_equity['realized_pnl'].cumsum()
    df_equity['trade_number'] = range(1, len(df_equity) + 1)
    
    # Create equity curve figure
    fig_equity = make_subplots(
        rows=2, cols=1,
        subplot_titles=('Cumulative R-Multiple', 'Cumulative P&L ($)'),
        vertical_spacing=0.12,
        row_heights=[0.5, 0.5]
    )
    
    # R-Multiple curve
    fig_equity.add_trace(
        go.Scatter(
            x=df_equity['trade_number'],
            y=df_equity['cumulative_r'],
            mode='lines+markers',
            name='Cumulative R',
            line=dict(color='#00D9FF', width=2),
            marker=dict(size=4),
            hovertemplate='Trade %{x}<br>Cumulative R: %{y:.2f}R<extra></extra>'
        ),
        row=1, col=1
    )
    
    # Add zero line
    fig_equity.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5, row=1, col=1)
    
    # P&L curve
    fig_equity.add_trace(
        go.Scatter(
            x=df_equity['trade_number'],
            y=df_equity['cumulative_pnl'],
            mode='lines+markers',
            name='Cumulative P&L',
            line=dict(color='#00FF9F', width=2),
            marker=dict(size=4),
            hovertemplate='Trade %{x}<br>P&L: $%{y:.2f}<extra></extra>'
        ),
        row=2, col=1
    )
    
    # Add zero line
    fig_equity.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5, row=2, col=1)
    
    # Update layout
    fig_equity.update_xaxes(title_text="Trade Number", row=2, col=1)
    fig_equity.update_yaxes(title_text="Cumulative R", row=1, col=1)
    fig_equity.update_yaxes(title_text="Cumulative $ P&L", row=2, col=1)
    
    fig_equity.update_layout(
        height=600,
        template="plotly_dark",
        showlegend=False,
        hovermode='x unified'
    )
    
    st.plotly_chart(fig_equity, use_container_width=True)
    
    st.markdown("---")
    
    # Visualization: Trade distribution by instrument
    st.markdown("### 📊 Trade Distribution")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Pie chart of trades by instrument
        fig_pie = go.Figure(data=[go.Pie(
            labels=df_comparison_numeric['Instrument'],
            values=df_comparison_numeric['Trades'],
            hole=0.4,
            marker=dict(colors=px.colors.qualitative.Set3)
        )])
        
        fig_pie.update_layout(
            title="Trades by Instrument",
            height=400,
            template="plotly_dark"
        )
        
        st.plotly_chart(fig_pie, use_container_width=True)
    
    with col2:
        # Bar chart of total R by instrument
        fig_bar = go.Figure(data=[go.Bar(
            x=df_comparison_numeric['Instrument'],
            y=df_comparison_numeric['Total R'],
            marker=dict(
                color=df_comparison_numeric['Total R'],
                colorscale='RdYlGn',
                showscale=True,
                cmin=-5,
                cmax=5
            ),
            text=df_comparison_numeric['Total R'].apply(lambda x: f"{x:.2f}R"),
            textposition='outside'
        )])
        
        fig_bar.update_layout(
            title="Total R-Multiple by Instrument",
            xaxis_title="Instrument",
            yaxis_title="Total R",
            height=400,
            template="plotly_dark",
            showlegend=False
        )
        
        fig_bar.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.5)
        
        st.plotly_chart(fig_bar, use_container_width=True)
    
    st.markdown("---")
    
    # Win rate comparison
    st.markdown("### 🎯 Win Rate vs Expectancy")
    
    fig_scatter = go.Figure()
    
    for _, row in df_comparison.iterrows():
        fig_scatter.add_trace(go.Scatter(
            x=[row['Win Rate']],
            y=[row['Expectancy']],
            mode='markers+text',
            name=row['Instrument'],
            text=row['Instrument'],
            textposition='top center',
            marker=dict(
                size=row['Trades'] * 3,  # Size by trade count
                sizemode='diameter',
                opacity=0.7
            )
        ))
    
    fig_scatter.update_layout(
        title="Win Rate vs Expectancy (bubble size = trade count)",
        xaxis_title="Win Rate",
        yaxis_title="Expectancy (R)",
        height=500,
        template="plotly_dark",
        hovermode='closest'
    )
    
    fig_scatter.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.5)
    fig_scatter.add_vline(x=0.5, line_dash="dash", line_color="white", opacity=0.5)
    
    st.plotly_chart(fig_scatter, use_container_width=True)
    
    st.markdown("---")
    
    # Governance section
    st.markdown("## 🛡️ Governance & Risk Management")
    
    governance = summary.get('governance_summary', {})
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Max Daily Loss", f"${governance.get('max_daily_loss', 0):,.2f}")
    
    with col2:
        st.metric("Max Drawdown", f"${governance.get('max_drawdown', 0):,.2f}")
    
    with col3:
        st.metric("Consecutive Losses (Max)", governance.get('max_consecutive_losses', 0))
    
    with col4:
        st.metric("Concurrent Trades (Max)", governance.get('max_concurrent_trades', 0))
    
    # Phase distribution
    if 'phase_distribution' in governance:
        st.markdown("### 📊 Capital Pacing Phase Distribution")
        
        phase_dist = governance['phase_distribution']
        phases = list(phase_dist.keys())
        days = list(phase_dist.values())
        
        fig_phases = go.Figure(data=[go.Bar(
            x=phases,
            y=days,
            marker=dict(
                color=['#2ECC71', '#3498DB', '#E74C3C'],  # Green, Blue, Red
            )
        )])
        
        fig_phases.update_layout(
            title="Days in Each Capital Pacing Phase",
            xaxis_title="Phase",
            yaxis_title="Days",
            height=400,
            template="plotly_dark",
            showlegend=False
        )
        
        st.plotly_chart(fig_phases, use_container_width=True)


def page_pre_session_rankings(run_id):
    """Pre-session instrument rankings page."""
    st.title("🏆 Pre-Session Rankings")
    
    # Check if rankings data exists
    run_path = Path("runs") / run_id
    rankings_file = run_path / "pre_session_rankings.json"
    
    if not rankings_file.exists():
        st.warning("No pre-session ranking data available for this run.")
        st.markdown("""
        Pre-session rankings help identify which instruments to focus on each day based on:
        - Overnight range vs typical ADR
        - Historical OR quality
        - Recent strategy performance
        - Volatility regime consistency
        - News risk (if available)
        
        This feature will be integrated in future updates.
        """)
        return
    
    # Load rankings data
    try:
        with open(rankings_file, 'r') as f:
            rankings_data = json.load(f)
    except Exception as e:
        st.error(f"Error loading rankings data: {e}")
        return
    
    st.markdown("## 📊 Daily Rankings Summary")
    
    # Date selector
    available_dates = sorted(rankings_data.keys(), reverse=True)
    selected_date = st.selectbox("Select Date", available_dates)
    
    if selected_date not in rankings_data:
        st.warning(f"No ranking data for {selected_date}")
        return
    
    day_rankings = rankings_data[selected_date]
    
    # Convert to DataFrame
    df_rankings = pd.DataFrame(day_rankings)
    df_rankings = df_rankings.sort_values('priority')
    
    # Display top recommendations
    st.markdown(f"### 🎯 Recommended Watch List for {selected_date}")
    
    recommended = df_rankings[df_rankings['recommended_watch'] == True]
    
    if len(recommended) > 0:
        cols = st.columns(len(recommended))
        for idx, (_, row) in enumerate(recommended.iterrows()):
            with cols[idx]:
                st.markdown(f"#### #{row['priority']} {row['symbol']}")
                st.metric("Score", f"{row['total_score']:.3f}")
                st.caption(row['reason'])
    else:
        st.info("No instruments recommended for trading on this date.")
    
    st.markdown("---")
    
    # Full rankings table
    st.markdown("### 📋 Complete Rankings")
    
    # Format display
    display_df = df_rankings[['priority', 'symbol', 'total_score', 'overnight_range_norm', 
                               'recent_win_rate', 'recent_expectancy', 'recommended_watch', 'reason']].copy()
    
    display_df.columns = ['Rank', 'Symbol', 'Score', 'ON Range', 'Win Rate', 'Expectancy', 'Watch', 'Reason']
    
    display_df['Score'] = display_df['Score'].apply(lambda x: f"{x:.3f}")
    display_df['ON Range'] = display_df['ON Range'].apply(lambda x: f"{x:.2f}x ADR")
    display_df['Win Rate'] = display_df['Win Rate'].apply(lambda x: f"{x*100:.1f}%")
    display_df['Expectancy'] = display_df['Expectancy'].apply(lambda x: f"{x:.2f}R")
    display_df['Watch'] = display_df['Watch'].apply(lambda x: "✅" if x else "")
    
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    
    st.markdown("---")
    
    # Component scores visualization
    st.markdown("### 📊 Score Components Breakdown")
    
    # Radar chart for each instrument
    fig = go.Figure()
    
    for _, row in df_rankings.iterrows():
        fig.add_trace(go.Scatterpolar(
            r=[
                row['overnight_range_score'],
                row['or_quality_score'],
                1.0 - row['news_risk_penalty'],  # Invert penalty
                row['vol_regime_score'],
                row['expectancy_score']
            ],
            theta=['Overnight Range', 'OR Quality', 'News Safety', 'Vol Regime', 'Expectancy'],
            fill='toself',
            name=row['symbol']
        ))
    
    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 1]
            )
        ),
        title="Score Components by Instrument",
        height=600,
        template="plotly_dark",
        showlegend=True
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("---")
    
    # Score trends over time
    st.markdown("### 📈 Score Trends Over Time")
    
    # Collect all dates for selected instrument
    symbol_selector = st.selectbox("Select Instrument", df_rankings['symbol'].tolist())
    
    trend_data = []
    for date in available_dates:
        date_rankings = rankings_data[date]
        symbol_ranking = next((r for r in date_rankings if r['symbol'] == symbol_selector), None)
        if symbol_ranking:
            trend_data.append({
                'date': date,
                'score': symbol_ranking['total_score'],
                'priority': symbol_ranking['priority']
            })
    
    df_trend = pd.DataFrame(trend_data)
    df_trend = df_trend.sort_values('date')
    
    if len(df_trend) > 0:
        fig_trend = make_subplots(
            rows=2, cols=1,
            subplot_titles=('Total Score', 'Priority Rank'),
            vertical_spacing=0.15
        )
        
        fig_trend.add_trace(
            go.Scatter(x=df_trend['date'], y=df_trend['score'], 
                      mode='lines+markers', name='Score',
                      line=dict(color='#3498DB', width=2)),
            row=1, col=1
        )
        
        fig_trend.add_trace(
            go.Scatter(x=df_trend['date'], y=df_trend['priority'], 
                      mode='lines+markers', name='Priority',
                      line=dict(color='#E74C3C', width=2)),
            row=2, col=1
        )
        
        fig_trend.update_yaxes(title_text="Score", row=1, col=1)
        fig_trend.update_yaxes(title_text="Rank", autorange="reversed", row=2, col=1)
        fig_trend.update_xaxes(title_text="Date", row=2, col=1)
        
        fig_trend.update_layout(
            height=600,
            template="plotly_dark",
            showlegend=False
        )
        
        st.plotly_chart(fig_trend, use_container_width=True)
    else:
        st.info(f"No trend data available for {symbol_selector}")


def get_enhanced_chart_config():
    """Get enhanced Plotly chart configuration."""
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
        'toImageButtonOptions': {
            'format': 'png',
            'filename': 'chart',
            'height': 1080,
            'width': 1920,
            'scale': 2
        }
    }
