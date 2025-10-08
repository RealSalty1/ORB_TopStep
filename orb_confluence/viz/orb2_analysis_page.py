"""ORB 2.0 Strategy Analysis Page - Comprehensive visualizations and insights."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import numpy as np
from datetime import datetime, timedelta


def create_equity_curve_with_drawdown(trades_df, starting_capital=100000, risk_per_trade_pct=0.01, 
                                     dollars_per_point=50):
    """Create equity curve with drawdown visualization showing real portfolio value.
    
    Args:
        trades_df: Trade data
        starting_capital: Starting portfolio value ($)
        risk_per_trade_pct: Risk per trade as % of capital (0.01 = 1%)
        dollars_per_point: Dollar value per point (ES = $50/point)
    """
    trades_sorted = trades_df.sort_values('exit_ts').copy()
    
    # Calculate actual dollar P&L for each trade
    # R-multiple * risk amount = dollar P&L
    trades_sorted['risk_amount'] = starting_capital * risk_per_trade_pct
    trades_sorted['dollar_pnl'] = trades_sorted['realized_r'] * trades_sorted['risk_amount']
    trades_sorted['portfolio_value'] = starting_capital + trades_sorted['dollar_pnl'].cumsum()
    
    # Calculate R-multiple cumulative (for reference)
    trades_sorted['cumulative_r'] = trades_sorted['realized_r'].cumsum()
    
    # Calculate drawdown in dollars
    trades_sorted['portfolio_max'] = trades_sorted['portfolio_value'].cummax()
    trades_sorted['drawdown_dollars'] = trades_sorted['portfolio_value'] - trades_sorted['portfolio_max']
    trades_sorted['drawdown_pct'] = (trades_sorted['drawdown_dollars'] / trades_sorted['portfolio_max']) * 100
    
    # Create subplots
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        subplot_titles=(
            f'Portfolio Value (Starting: ${starting_capital:,.0f})', 
            'Drawdown ($)', 
            'Drawdown (%)'
        ),
        row_heights=[0.5, 0.25, 0.25]
    )
    
    # Portfolio value curve
    fig.add_trace(
        go.Scatter(
            x=trades_sorted['exit_ts'],
            y=trades_sorted['portfolio_value'],
            mode='lines',
            name='Portfolio Value',
            line=dict(color='#00ff88', width=2.5),
            fill='tozeroy',
            fillcolor='rgba(0, 255, 136, 0.1)',
            hovertemplate='<b>%{y:$,.0f}</b><br>%{x}<extra></extra>',
        ),
        row=1, col=1
    )
    
    # Add starting capital line
    fig.add_hline(
        y=starting_capital, 
        line_dash="dash", 
        line_color="cyan", 
        opacity=0.5, 
        row=1, col=1,
        annotation_text=f"Start: ${starting_capital:,.0f}",
        annotation_position="right"
    )
    
    # Drawdown in dollars
    fig.add_trace(
        go.Scatter(
            x=trades_sorted['exit_ts'],
            y=trades_sorted['drawdown_dollars'],
            mode='lines',
            name='Drawdown ($)',
            line=dict(color='#ff6b6b', width=2),
            fill='tozeroy',
            fillcolor='rgba(255, 107, 107, 0.2)',
            hovertemplate='<b>%{y:$,.0f}</b><br>%{x}<extra></extra>',
        ),
        row=2, col=1
    )
    
    # Drawdown in percentage
    fig.add_trace(
        go.Scatter(
            x=trades_sorted['exit_ts'],
            y=trades_sorted['drawdown_pct'],
            mode='lines',
            name='Drawdown (%)',
            line=dict(color='#ff4757', width=2),
            fill='tozeroy',
            fillcolor='rgba(255, 71, 87, 0.2)',
            hovertemplate='<b>%{y:.2f}%</b><br>%{x}<extra></extra>',
        ),
        row=3, col=1
    )
    
    # Add zero lines
    fig.add_hline(y=0, line_dash="solid", line_color="gray", opacity=0.3, row=2, col=1)
    fig.add_hline(y=0, line_dash="solid", line_color="gray", opacity=0.3, row=3, col=1)
    
    fig.update_xaxes(title_text="Date", row=3, col=1)
    fig.update_yaxes(title_text="Portfolio Value ($)", row=1, col=1)
    fig.update_yaxes(title_text="Drawdown ($)", row=2, col=1)
    fig.update_yaxes(title_text="Drawdown (%)", row=3, col=1)
    
    fig.update_layout(
        height=800,
        template="plotly_dark",
        hovermode='x unified',
        showlegend=True,
    )
    
    return fig, trades_sorted


def create_mfe_mae_analysis(trades_df):
    """Enhanced MFE vs MAE scatter with insights."""
    fig = go.Figure()
    
    # Winners
    winners = trades_df[trades_df['realized_r'] > 0]
    fig.add_trace(go.Scatter(
        x=winners['mae_r'],
        y=winners['mfe_r'],
        mode='markers',
        name=f'Winners ({len(winners)})',
        marker=dict(
            color=winners['realized_r'],
            size=8,
            opacity=0.7,
            colorscale='Greens',
            showscale=True,
            colorbar=dict(title="Realized R", x=1.15),
        ),
        text=[f"{row['trade_id']}<br>R: {row['realized_r']:.2f}" for _, row in winners.iterrows()],
        hovertemplate='<b>%{text}</b><br>MAE: %{x:.2f}R<br>MFE: %{y:.2f}R<extra></extra>',
    ))
    
    # Losers
    losers = trades_df[trades_df['realized_r'] <= 0]
    fig.add_trace(go.Scatter(
        x=losers['mae_r'],
        y=losers['mfe_r'],
        mode='markers',
        name=f'Losers ({len(losers)})',
        marker=dict(
            color=losers['realized_r'],
            size=6,
            opacity=0.4,
            colorscale='Reds',
            reversescale=True,
        ),
        text=[f"{row['trade_id']}<br>R: {row['realized_r']:.2f}" for _, row in losers.iterrows()],
        hovertemplate='<b>%{text}</b><br>MAE: %{x:.2f}R<br>MFE: %{y:.2f}R<extra></extra>',
    ))
    
    # Add reference lines
    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.3)
    fig.add_vline(x=0, line_dash="dash", line_color="gray", opacity=0.3)
    
    # Add diagonal line (MFE = MAE in absolute terms)
    max_val = max(trades_df['mfe_r'].max(), abs(trades_df['mae_r'].min()))
    fig.add_trace(go.Scatter(
        x=[-max_val, 0],
        y=[0, max_val],
        mode='lines',
        name='MFE = |MAE|',
        line=dict(color='yellow', dash='dot', width=1),
        showlegend=True,
    ))
    
    fig.update_layout(
        title="MFE vs MAE Path Analysis",
        xaxis_title="Max Adverse Excursion (MAE) [R]",
        yaxis_title="Max Favorable Excursion (MFE) [R]",
        height=600,
        template="plotly_dark",
        hovermode='closest',
    )
    
    return fig


def create_win_loss_streak_analysis(trades_df):
    """Analyze win/loss streaks."""
    trades_sorted = trades_df.sort_values('exit_ts').copy()
    trades_sorted['is_winner'] = trades_sorted['realized_r'] > 0
    
    # Calculate streaks
    trades_sorted['streak_change'] = trades_sorted['is_winner'].ne(trades_sorted['is_winner'].shift())
    trades_sorted['streak_id'] = trades_sorted['streak_change'].cumsum()
    
    streaks = trades_sorted.groupby('streak_id').agg({
        'is_winner': 'first',
        'exit_ts': ['first', 'count'],
    })
    streaks.columns = ['is_winner', 'exit_ts', 'streak_length']
    streaks = streaks.reset_index(drop=True)
    
    # Create visualization
    fig = go.Figure()
    
    # Winning streaks
    win_streaks = streaks[streaks['is_winner']]
    fig.add_trace(go.Bar(
        x=win_streaks['exit_ts'],
        y=win_streaks['streak_length'],
        name='Win Streaks',
        marker_color='green',
        text=win_streaks['streak_length'],
        textposition='outside',
    ))
    
    # Losing streaks
    loss_streaks = streaks[~streaks['is_winner']]
    fig.add_trace(go.Bar(
        x=loss_streaks['exit_ts'],
        y=-loss_streaks['streak_length'],  # Negative for visual separation
        name='Loss Streaks',
        marker_color='red',
        text=loss_streaks['streak_length'],
        textposition='outside',
    ))
    
    fig.add_hline(y=0, line_color="white", line_width=1)
    
    fig.update_layout(
        title="Win/Loss Streak Analysis",
        xaxis_title="Date",
        yaxis_title="Streak Length (Consecutive Trades)",
        height=400,
        template="plotly_dark",
        showlegend=True,
        barmode='relative',
    )
    
    return fig, streaks


def create_time_of_day_analysis(trades_df):
    """Analyze performance by time of day."""
    trades_copy = trades_df.copy()
    
    # Extract hour from exit timestamp
    trades_copy['hour'] = pd.to_datetime(trades_copy['exit_ts']).dt.hour
    
    # Group by hour
    hourly_stats = trades_copy.groupby('hour').agg({
        'realized_r': ['sum', 'mean'],
        'trade_id': 'count'
    }).round(3)
    
    hourly_stats.columns = ['total_r', 'avg_r', 'num_trades']
    hourly_stats = hourly_stats.reset_index()
    
    # Create dual-axis chart
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    # Total R by hour (bar)
    fig.add_trace(
        go.Bar(
            x=hourly_stats['hour'],
            y=hourly_stats['total_r'],
            name='Total R',
            marker_color=['green' if r > 0 else 'red' for r in hourly_stats['total_r']],
            text=hourly_stats['total_r'].round(2),
            textposition='outside',
        ),
        secondary_y=False,
    )
    
    # Number of trades (line)
    fig.add_trace(
        go.Scatter(
            x=hourly_stats['hour'],
            y=hourly_stats['num_trades'],
            name='# Trades',
            mode='lines+markers',
            line=dict(color='cyan', width=2),
            marker=dict(size=8),
        ),
        secondary_y=True,
    )
    
    fig.update_xaxes(title_text="Hour of Day (UTC)", dtick=1)
    fig.update_yaxes(title_text="Total R", secondary_y=False)
    fig.update_yaxes(title_text="Number of Trades", secondary_y=True)
    
    fig.update_layout(
        title="Performance by Time of Day",
        height=400,
        template="plotly_dark",
        hovermode='x unified',
    )
    
    return fig, hourly_stats


def create_returns_distribution_comparison(trades_df):
    """Compare winners vs losers distribution."""
    winners = trades_df[trades_df['realized_r'] > 0]['realized_r']
    losers = trades_df[trades_df['realized_r'] <= 0]['realized_r']
    
    fig = go.Figure()
    
    # Winners histogram
    fig.add_trace(go.Histogram(
        x=winners,
        name=f'Winners (n={len(winners)})',
        marker_color='green',
        opacity=0.7,
        nbinsx=50,
    ))
    
    # Losers histogram
    fig.add_trace(go.Histogram(
        x=losers,
        name=f'Losers (n={len(losers)})',
        marker_color='red',
        opacity=0.7,
        nbinsx=50,
    ))
    
    # Add mean lines
    fig.add_vline(x=winners.mean(), line_dash="dash", line_color="green", 
                  annotation_text=f"Win Avg: {winners.mean():.3f}R")
    fig.add_vline(x=losers.mean(), line_dash="dash", line_color="red",
                  annotation_text=f"Loss Avg: {losers.mean():.3f}R")
    
    fig.update_layout(
        title="Returns Distribution: Winners vs Losers",
        xaxis_title="Realized R",
        yaxis_title="Count",
        height=400,
        template="plotly_dark",
        barmode='overlay',
    )
    
    return fig


def create_monthly_heatmap(trades_df):
    """Create monthly performance heatmap."""
    trades_copy = trades_df.copy()
    trades_copy['exit_date'] = pd.to_datetime(trades_copy['exit_ts'])
    trades_copy['year_month'] = trades_copy['exit_date'].dt.to_period('M')
    trades_copy['day'] = trades_copy['exit_date'].dt.day
    
    # Aggregate daily returns
    daily_agg = trades_copy.groupby(['year_month', 'day'])['realized_r'].sum().reset_index()
    daily_agg.columns = ['year_month', 'day', 'total_r']
    daily_agg['year_month'] = daily_agg['year_month'].astype(str)
    
    # Pivot for heatmap
    heatmap_data = daily_agg.pivot(index='day', columns='year_month', values='total_r')
    
    fig = go.Figure(data=go.Heatmap(
        z=heatmap_data.values,
        x=heatmap_data.columns,
        y=heatmap_data.index,
        colorscale='RdYlGn',
        zmid=0,
        text=heatmap_data.values.round(2),
        texttemplate='%{text}',
        textfont={"size": 8},
        colorbar=dict(title="Daily R"),
    ))
    
    fig.update_layout(
        title="Daily Performance Heatmap by Month",
        xaxis_title="Month",
        yaxis_title="Day of Month",
        height=600,
        template="plotly_dark",
    )
    
    return fig


def create_salvage_analysis(trades_df):
    """Analyze salvage exits vs regular stops."""
    if 'salvage_triggered' not in trades_df.columns:
        return None
    
    salvage_trades = trades_df[trades_df['salvage_triggered'] == True]
    stop_trades = trades_df[(trades_df['exit_reason'] == 'STOP') & (trades_df['salvage_triggered'] == False)]
    
    if len(salvage_trades) == 0:
        return None
    
    fig = go.Figure()
    
    # Salvage exits
    fig.add_trace(go.Scatter(
        x=salvage_trades['mfe_r'],
        y=salvage_trades['realized_r'],
        mode='markers',
        name=f'Salvage Exits ({len(salvage_trades)})',
        marker=dict(
            color='orange',
            size=10,
            symbol='diamond',
        ),
        text=[f"{row['trade_id']}<br>MFE: {row['mfe_r']:.2f}R<br>Exit: {row['realized_r']:.2f}R" 
              for _, row in salvage_trades.iterrows()],
        hovertemplate='%{text}<extra></extra>',
    ))
    
    # Regular stops (sample for comparison)
    if len(stop_trades) > 0:
        sample_stops = stop_trades.sample(min(100, len(stop_trades)))
        fig.add_trace(go.Scatter(
            x=sample_stops['mfe_r'],
            y=sample_stops['realized_r'],
            mode='markers',
            name='Regular Stops (sample)',
            marker=dict(
                color='gray',
                size=6,
                opacity=0.3,
            ),
        ))
    
    fig.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.5)
    
    fig.update_layout(
        title="Salvage Exit Analysis: MFE vs Exit R",
        xaxis_title="Max Favorable Excursion (MFE) [R]",
        yaxis_title="Realized R at Exit",
        height=500,
        template="plotly_dark",
    )
    
    return fig


def page_orb2_analysis(run_data):
    """Main ORB 2.0 analysis page."""
    st.title("📊 ORB 2.0 Strategy Analysis")
    
    trades_df = run_data.get('trades')
    metrics = run_data.get('metrics')
    
    if trades_df is None or len(trades_df) == 0:
        st.warning("No trade data available for analysis.")
        return
    
    # Portfolio Performance Section
    st.markdown("## 💰 Portfolio Performance")
    
    # Settings row
    col1, col2, col3 = st.columns(3)
    with col1:
        starting_capital = st.number_input(
            "Starting Capital ($)", 
            min_value=10000, 
            max_value=1000000, 
            value=100000, 
            step=10000,
            key="portfolio_starting_capital"
        )
    with col2:
        risk_pct = st.slider(
            "Risk per Trade (%)", 
            min_value=0.5, 
            max_value=5.0, 
            value=1.0, 
            step=0.5,
            key="portfolio_risk_pct"
        )
    with col3:
        dollars_per_point = st.number_input(
            "$ per Point", 
            min_value=1, 
            max_value=100, 
            value=50,
            help="ES=$50, NQ=$20, GC=$100",
            key="portfolio_dollars_per_point"
        )
    
    # Calculate portfolio metrics
    trades_sorted = trades_df.sort_values('exit_ts').copy()
    trades_sorted['risk_amount'] = starting_capital * (risk_pct/100)
    trades_sorted['dollar_pnl'] = trades_sorted['realized_r'] * trades_sorted['risk_amount']
    trades_sorted['portfolio_value'] = starting_capital + trades_sorted['dollar_pnl'].cumsum()
    trades_sorted['portfolio_max'] = trades_sorted['portfolio_value'].cummax()
    trades_sorted['drawdown_dollars'] = trades_sorted['portfolio_value'] - trades_sorted['portfolio_max']
    trades_sorted['drawdown_pct'] = (trades_sorted['drawdown_dollars'] / trades_sorted['portfolio_max']) * 100
    
    # Display key portfolio metrics
    final_value = trades_sorted['portfolio_value'].iloc[-1]
    total_return_dollars = final_value - starting_capital
    total_return_pct = (total_return_dollars / starting_capital) * 100
    max_dd_dollars = trades_sorted['drawdown_dollars'].min()
    max_dd_pct = trades_sorted['drawdown_pct'].min()
    
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Starting Capital", f"${starting_capital:,.0f}")
    with col2:
        st.metric("Final Value", f"${final_value:,.0f}", 
                 delta=f"+${total_return_dollars:,.0f}")
    with col3:
        st.metric("Total Return", f"+{total_return_pct:.2f}%",
                 delta=f"+${total_return_dollars:,.0f}")
    with col4:
        st.metric("Max Drawdown", f"{max_dd_pct:.2f}%",
                 delta=f"-${abs(max_dd_dollars):,.0f}")
    with col5:
        profit_factor = (
            trades_sorted[trades_sorted['dollar_pnl'] > 0]['dollar_pnl'].sum() /
            abs(trades_sorted[trades_sorted['dollar_pnl'] < 0]['dollar_pnl'].sum())
        )
        st.metric("Profit Factor", f"{profit_factor:.2f}")
    
    st.markdown("---")
    
    # Trade Statistics
    st.markdown("## 📈 Trade Statistics")
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    
    with col1:
        st.metric("Total Trades", f"{len(trades_df):,}")
    with col2:
        win_rate = (trades_df['realized_r'] > 0).sum() / len(trades_df) * 100
        st.metric("Win Rate", f"{win_rate:.1f}%")
    with col3:
        expectancy = trades_df['realized_r'].mean()
        st.metric("Expectancy", f"{expectancy:.4f}R", 
                  delta="Positive" if expectancy > 0 else "Negative")
    with col4:
        total_r = trades_df['realized_r'].sum()
        st.metric("Total R", f"+{total_r:.2f}R")
    with col5:
        avg_winner = trades_df[trades_df['realized_r'] > 0]['realized_r'].mean()
        st.metric("Avg Winner", f"+{avg_winner:.2f}R")
    with col6:
        avg_loser = trades_df[trades_df['realized_r'] <= 0]['realized_r'].mean()
        st.metric("Avg Loser", f"{avg_loser:.2f}R")
    
    st.markdown("---")
    
    # Tabs for different analyses
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📈 Equity & Drawdown",
        "🎯 MFE/MAE Analysis", 
        "📊 Distributions",
        "⏰ Time Analysis",
        "🔄 Streak Analysis",
        "💡 Salvage Analysis"
    ])
    
    with tab1:
        st.markdown("### Portfolio Equity Curve")
        
        # Settings
        col1, col2, col3 = st.columns(3)
        with col1:
            starting_capital = st.number_input(
                "Starting Capital ($)", 
                min_value=10000, 
                max_value=1000000, 
                value=100000, 
                step=10000,
                help="Initial portfolio value"
            )
        with col2:
            risk_pct = st.slider(
                "Risk per Trade (%)", 
                min_value=0.5, 
                max_value=5.0, 
                value=1.0, 
                step=0.5,
                help="Percentage of capital risked per trade"
            )
        with col3:
            dollars_per_point = st.number_input(
                "$ per Point", 
                min_value=1, 
                max_value=100, 
                value=50,
                help="ES = $50, NQ = $20, etc."
            )
        
        fig, equity_df = create_equity_curve_with_drawdown(
            trades_df, 
            starting_capital=starting_capital,
            risk_per_trade_pct=risk_pct/100,
            dollars_per_point=dollars_per_point
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # Portfolio statistics
        st.markdown("### Portfolio Statistics")
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        
        final_value = equity_df['portfolio_value'].iloc[-1]
        total_return = final_value - starting_capital
        return_pct = (total_return / starting_capital) * 100
        max_dd_dollars = equity_df['drawdown_dollars'].min()
        max_dd_pct = equity_df['drawdown_pct'].min()
        current_dd_dollars = equity_df['drawdown_dollars'].iloc[-1]
        
        with col1:
            st.metric("Starting Capital", f"${starting_capital:,.0f}")
        with col2:
            st.metric("Final Value", f"${final_value:,.0f}", 
                     delta=f"${total_return:,.0f}")
        with col3:
            st.metric("Total Return", f"{return_pct:+.2f}%",
                     delta=f"${total_return:,.0f}")
        with col4:
            st.metric("Max Drawdown", f"${abs(max_dd_dollars):,.0f}",
                     delta=f"{max_dd_pct:.2f}%")
        with col5:
            st.metric("Current Drawdown", f"${abs(current_dd_dollars):,.0f}")
        with col6:
            recovery_count = len(equity_df[equity_df['drawdown_dollars'] == 0])
            st.metric("New Equity Highs", recovery_count)
        
        # Additional metrics
        st.markdown("### Risk & Return Metrics")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            avg_trade_pnl = equity_df['dollar_pnl'].mean()
            st.metric("Avg Trade P&L", f"${avg_trade_pnl:,.0f}")
        with col2:
            max_win = equity_df['dollar_pnl'].max()
            st.metric("Largest Win", f"${max_win:,.0f}")
        with col3:
            max_loss = equity_df['dollar_pnl'].min()
            st.metric("Largest Loss", f"${max_loss:,.0f}")
        with col4:
            profit_factor = (
                equity_df[equity_df['dollar_pnl'] > 0]['dollar_pnl'].sum() /
                abs(equity_df[equity_df['dollar_pnl'] < 0]['dollar_pnl'].sum())
            )
            st.metric("Profit Factor", f"{profit_factor:.2f}")
        
        # Position sizing info
        st.markdown("### Position Sizing")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            risk_amount = starting_capital * (risk_pct / 100)
            st.metric("Risk per Trade", f"${risk_amount:,.0f}",
                     help=f"{risk_pct}% of ${starting_capital:,.0f}")
        with col2:
            # Example: if stop is 20 points and $50/point = $1000 risk
            # Then contracts = $1000 / ($1000) = 1 contract
            example_stop_points = 20
            example_risk_dollars = example_stop_points * dollars_per_point
            contracts = max(1, int(risk_amount / example_risk_dollars))
            st.metric("Contracts (20pt stop)", f"{contracts}",
                     help=f"For a 20-point stop @ ${dollars_per_point}/pt")
        with col3:
            max_risk_dollars = contracts * 20 * dollars_per_point
            st.metric("Max $ Risk (20pt)", f"${max_risk_dollars:,.0f}")
        
        # Monthly performance
        st.markdown("### Monthly Performance")
        monthly_fig = create_monthly_heatmap(trades_df)
        st.plotly_chart(monthly_fig, use_container_width=True)
    
    with tab2:
        st.markdown("### MFE vs MAE Analysis")
        fig = create_mfe_mae_analysis(trades_df)
        st.plotly_chart(fig, use_container_width=True)
        
        # MFE/MAE insights
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("#### Winners")
            winners = trades_df[trades_df['realized_r'] > 0]
            st.metric("Avg MFE", f"{winners['mfe_r'].mean():.2f}R")
            st.metric("Avg MAE", f"{winners['mae_r'].mean():.2f}R")
            st.metric("MFE/MAE Ratio", f"{abs(winners['mfe_r'].mean() / winners['mae_r'].mean()):.1f}:1")
        
        with col2:
            st.markdown("#### Losers")
            losers = trades_df[trades_df['realized_r'] <= 0]
            st.metric("Avg MFE", f"{losers['mfe_r'].mean():.2f}R")
            st.metric("Avg MAE", f"{losers['mae_r'].mean():.2f}R")
            
            # Opportunity cost
            losers_with_mfe = losers[losers['mfe_r'] > 0.10]
            st.metric("Losers with >0.10R MFE", f"{len(losers_with_mfe)} ({len(losers_with_mfe)/len(losers)*100:.1f}%)")
        
        with col3:
            st.markdown("#### Overall")
            st.metric("Avg MFE (All)", f"{trades_df['mfe_r'].mean():.2f}R")
            st.metric("Avg MAE (All)", f"{trades_df['mae_r'].mean():.2f}R")
            
            # Potential improvement
            potential = losers_with_mfe['mfe_r'].sum() * 0.5  # If we captured 50% of MFE
            st.metric("Potential Gain", f"+{potential:.2f}R", help="If partial exits captured 50% of MFE from losers with >0.10R MFE")
    
    with tab3:
        st.markdown("### Returns Distribution")
        fig = create_returns_distribution_comparison(trades_df)
        st.plotly_chart(fig, use_container_width=True)
        
        # Exit reason breakdown
        st.markdown("### Exit Reason Analysis")
        exit_counts = trades_df['exit_reason'].value_counts()
        
        col1, col2 = st.columns(2)
        with col1:
            fig_pie = go.Figure(data=[go.Pie(
                labels=exit_counts.index,
                values=exit_counts.values,
                hole=0.4,
            )])
            fig_pie.update_layout(
                title="Exit Reasons",
                height=400,
                template="plotly_dark",
            )
            st.plotly_chart(fig_pie, use_container_width=True)
        
        with col2:
            # Exit reason performance
            exit_performance = trades_df.groupby('exit_reason')['realized_r'].agg(['count', 'sum', 'mean']).round(3)
            exit_performance.columns = ['Count', 'Total R', 'Avg R']
            st.dataframe(exit_performance, use_container_width=True)
    
    with tab4:
        st.markdown("### Time of Day Analysis")
        fig, hourly_stats = create_time_of_day_analysis(trades_df)
        st.plotly_chart(fig, use_container_width=True)
        
        # Best/worst hours
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### Best Hours")
            best_hours = hourly_stats.nlargest(5, 'total_r')[['hour', 'total_r', 'num_trades', 'avg_r']]
            st.dataframe(best_hours, use_container_width=True, hide_index=True)
        
        with col2:
            st.markdown("#### Worst Hours")
            worst_hours = hourly_stats.nsmallest(5, 'total_r')[['hour', 'total_r', 'num_trades', 'avg_r']]
            st.dataframe(worst_hours, use_container_width=True, hide_index=True)
        
        # Day of week analysis
        st.markdown("### Day of Week Analysis")
        trades_df_copy = trades_df.copy()
        trades_df_copy['day_of_week'] = pd.to_datetime(trades_df_copy['exit_ts']).dt.day_name()
        daily_stats = trades_df_copy.groupby('day_of_week')['realized_r'].agg(['count', 'sum', 'mean']).round(3)
        daily_stats.columns = ['Count', 'Total R', 'Avg R']
        
        # Reorder days
        day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        daily_stats = daily_stats.reindex([d for d in day_order if d in daily_stats.index])
        
        st.dataframe(daily_stats, use_container_width=True)
    
    with tab5:
        st.markdown("### Win/Loss Streak Analysis")
        fig, streaks = create_win_loss_streak_analysis(trades_df)
        st.plotly_chart(fig, use_container_width=True)
        
        # Streak statistics
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### Winning Streaks")
            win_streaks = streaks[streaks['is_winner']]
            st.metric("Max Win Streak", f"{win_streaks['streak_length'].max()} trades")
            st.metric("Avg Win Streak", f"{win_streaks['streak_length'].mean():.1f} trades")
            st.metric("Total Win Streaks", len(win_streaks))
        
        with col2:
            st.markdown("#### Losing Streaks")
            loss_streaks = streaks[~streaks['is_winner']]
            st.metric("Max Loss Streak", f"{loss_streaks['streak_length'].max()} trades")
            st.metric("Avg Loss Streak", f"{loss_streaks['streak_length'].mean():.1f} trades")
            st.metric("Total Loss Streaks", len(loss_streaks))
    
    with tab6:
        if 'salvage_triggered' in trades_df.columns:
            st.markdown("### Salvage Exit Analysis")
            fig = create_salvage_analysis(trades_df)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
                
                # Salvage statistics
                salvage_trades = trades_df[trades_df['salvage_triggered'] == True]
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Total Salvages", len(salvage_trades))
                with col2:
                    salvage_r = salvage_trades['realized_r'].sum()
                    st.metric("Total Salvage R", f"+{salvage_r:.2f}R")
                with col3:
                    avg_salvage_r = salvage_trades['realized_r'].mean()
                    st.metric("Avg Salvage R", f"+{avg_salvage_r:.2f}R")
                with col4:
                    avg_mfe_before = salvage_trades['mfe_r'].mean()
                    st.metric("Avg MFE Before Salvage", f"{avg_mfe_before:.2f}R")
                
                # Salvage effectiveness
                st.markdown("#### Salvage Effectiveness")
                st.write(f"**Benefit**: Without salvage, these {len(salvage_trades)} trades would have likely stopped out at full loss.")
                estimated_benefit = len(salvage_trades) * (avg_salvage_r + 0.05)  # Assuming avg -0.05R if not salvaged
                st.metric("Estimated Salvage Benefit", f"+{estimated_benefit:.2f}R", 
                         help="Estimated R saved by salvage exits vs full stop losses")
            else:
                st.info("No salvage exits in this backtest.")
        else:
            st.info("Salvage data not available for this backtest run.")

