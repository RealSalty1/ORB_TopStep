"""Plotting helper functions."""

import plotly.graph_objects as go


def plot_equity_curve(equity_data: list) -> go.Figure:
    """Create equity curve plot.

    Args:
        equity_data: List of dicts with timestamp and cumulative_r.

    Returns:
        Plotly Figure.
    """
    # TODO: Implement equity curve plotting
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=[d["timestamp"] for d in equity_data],
            y=[d["cumulative_r"] for d in equity_data],
            mode="lines",
            name="Equity Curve",
        )
    )
    fig.update_layout(title="Equity Curve (R-based)", xaxis_title="Date", yaxis_title="Cumulative R")
    return fig


def plot_r_distribution(r_values: list) -> go.Figure:
    """Create R distribution histogram.

    Args:
        r_values: List of R values.

    Returns:
        Plotly Figure.
    """
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=r_values, nbinsx=30))
    fig.update_layout(title="R Distribution", xaxis_title="R Multiple", yaxis_title="Frequency")
    return fig
