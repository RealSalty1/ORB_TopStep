"""HTML report generator with embedded charts."""

from pathlib import Path
from typing import Optional

import plotly.graph_objects as go
import plotly.express as px
from jinja2 import Template
from loguru import logger

from ..backtest.engine import BacktestResult
from ..analytics.metrics import PerformanceAnalyzer


class HTMLReportGenerator:
    """Generates comprehensive HTML backtest report.

    Includes:
    - Summary metrics
    - Equity curve chart
    - Trade distribution
    - Factor attribution
    - OR statistics
    """

    def __init__(self) -> None:
        """Initialize HTML report generator."""
        self.template = self._get_template()

    def generate(
        self,
        result: BacktestResult,
        output_path: Path,
    ) -> None:
        """Generate HTML report.

        Args:
            result: Backtest result.
            output_path: Path to save HTML file.
        """
        logger.info(f"Generating HTML report: {output_path}")

        # Analyze results
        analyzer = PerformanceAnalyzer(result)

        # Generate charts
        equity_chart = self._create_equity_chart(result)
        r_distribution_chart = self._create_r_distribution_chart(result)
        factor_chart = self._create_factor_attribution_chart(analyzer)

        # Render template
        html = self.template.render(
            result=result,
            equity_chart=equity_chart,
            r_distribution_chart=r_distribution_chart,
            factor_chart=factor_chart,
            factor_attribution=analyzer.factor_attribution().to_html(index=False),
            score_tiers=analyzer.score_tier_analysis().to_html(index=False),
            drawdown_stats=analyzer.drawdown_analysis(),
        )

        # Save
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html)

        logger.info(f"HTML report saved to {output_path}")

    def _create_equity_chart(self, result: BacktestResult) -> str:
        """Create equity curve chart.

        Args:
            result: Backtest result.

        Returns:
            HTML div with chart.
        """
        if result.equity_curve is None or result.equity_curve.empty:
            return "<p>No equity data available</p>"

        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=result.equity_curve.index,
            y=result.equity_curve["cumulative_r"],
            mode="lines",
            name="Cumulative R",
            line=dict(color="blue", width=2),
        ))

        fig.update_layout(
            title="Equity Curve (R-based)",
            xaxis_title="Date",
            yaxis_title="Cumulative R",
            template="plotly_white",
            height=400,
        )

        return fig.to_html(full_html=False, include_plotlyjs="cdn")

    def _create_r_distribution_chart(self, result: BacktestResult) -> str:
        """Create R distribution histogram.

        Args:
            result: Backtest result.

        Returns:
            HTML div with chart.
        """
        if not result.trades:
            return "<p>No trades available</p>"

        r_values = [t.realized_r for t in result.trades]

        fig = go.Figure()

        fig.add_trace(go.Histogram(
            x=r_values,
            nbinsx=30,
            name="R Distribution",
            marker=dict(color="steelblue"),
        ))

        fig.update_layout(
            title="Trade R Distribution",
            xaxis_title="R Multiple",
            yaxis_title="Frequency",
            template="plotly_white",
            height=400,
        )

        return fig.to_html(full_html=False, include_plotlyjs="cdn")

    def _create_factor_attribution_chart(self, analyzer: PerformanceAnalyzer) -> str:
        """Create factor attribution bar chart.

        Args:
            analyzer: Performance analyzer.

        Returns:
            HTML div with chart.
        """
        factor_df = analyzer.factor_attribution()

        if factor_df.empty:
            return "<p>No factor data available</p>"

        fig = go.Figure()

        fig.add_trace(go.Bar(
            x=factor_df["factor"],
            y=factor_df["avg_r"],
            name="Avg R",
            marker=dict(color="green"),
        ))

        fig.update_layout(
            title="Factor Attribution (Avg R)",
            xaxis_title="Factor",
            yaxis_title="Average R",
            template="plotly_white",
            height=400,
        )

        return fig.to_html(full_html=False, include_plotlyjs="cdn")

    @staticmethod
    def _get_template() -> Template:
        """Get HTML template.

        Returns:
            Jinja2 template.
        """
        template_str = """
<!DOCTYPE html>
<html>
<head>
    <title>ORB Strategy Backtest Report</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            border-bottom: 3px solid #4CAF50;
            padding-bottom: 10px;
        }
        h2 {
            color: #555;
            margin-top: 30px;
            border-bottom: 2px solid #ddd;
            padding-bottom: 5px;
        }
        .metrics {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }
        .metric-card {
            background-color: #f9f9f9;
            padding: 15px;
            border-radius: 5px;
            border-left: 4px solid #4CAF50;
        }
        .metric-label {
            font-size: 12px;
            color: #777;
            text-transform: uppercase;
        }
        .metric-value {
            font-size: 24px;
            font-weight: bold;
            color: #333;
            margin-top: 5px;
        }
        .positive {
            color: #4CAF50;
        }
        .negative {
            color: #f44336;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }
        th, td {
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th {
            background-color: #4CAF50;
            color: white;
        }
        tr:hover {
            background-color: #f5f5f5;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>ORB Strategy Backtest Report</h1>
        <p><strong>Run ID:</strong> {{ result.run_id }}</p>
        <p><strong>Strategy:</strong> {{ result.config.name }} v{{ result.config.version }}</p>
        <p><strong>Period:</strong> {{ result.config.backtest.start_date }} to {{ result.config.backtest.end_date }}</p>
        
        <h2>Summary Metrics</h2>
        <div class="metrics">
            <div class="metric-card">
                <div class="metric-label">Total Trades</div>
                <div class="metric-value">{{ result.total_trades }}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Win Rate</div>
                <div class="metric-value {{ 'positive' if result.win_rate > 0.5 else '' }}">{{ "%.1f"|format(result.win_rate * 100) }}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Avg R</div>
                <div class="metric-value {{ 'positive' if result.avg_r > 0 else 'negative' }}">{{ "%.2f"|format(result.avg_r) }}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Total R</div>
                <div class="metric-value {{ 'positive' if result.total_r > 0 else 'negative' }}">{{ "%.2f"|format(result.total_r) }}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Expectancy</div>
                <div class="metric-value {{ 'positive' if result.expectancy > 0 else 'negative' }}">{{ "%.2f"|format(result.expectancy) }}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Profit Factor</div>
                <div class="metric-value">{{ "%.2f"|format(result.profit_factor) if result.profit_factor != float('inf') else '∞' }}</div>
            </div>
        </div>

        <h2>Equity Curve</h2>
        {{ equity_chart|safe }}

        <h2>R Distribution</h2>
        {{ r_distribution_chart|safe }}

        <h2>Factor Attribution</h2>
        {{ factor_chart|safe }}
        {{ factor_attribution|safe }}

        <h2>Score Tier Analysis</h2>
        {{ score_tiers|safe }}

        <h2>Drawdown Statistics</h2>
        <div class="metrics">
            <div class="metric-card">
                <div class="metric-label">Max Drawdown (R)</div>
                <div class="metric-value negative">{{ "%.2f"|format(drawdown_stats.max_drawdown_r) }}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Max Drawdown (%)</div>
                <div class="metric-value negative">{{ "%.1f"|format(drawdown_stats.max_drawdown_pct * 100) }}%</div>
            </div>
        </div>

        <h2>Opening Range Statistics</h2>
        <div class="metrics">
            <div class="metric-card">
                <div class="metric-label">Valid ORs</div>
                <div class="metric-value">{{ result.or_valid_count }}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Invalid ORs</div>
                <div class="metric-value">{{ result.or_invalid_count }}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Validity Rate</div>
                <div class="metric-value">{{ "%.1f"|format(result.or_valid_count / (result.or_valid_count + result.or_invalid_count) * 100 if (result.or_valid_count + result.or_invalid_count) > 0 else 0) }}%</div>
            </div>
        </div>

        <footer style="margin-top: 50px; padding-top: 20px; border-top: 1px solid #ddd; color: #777; text-align: center;">
            <p>Generated by ORB Strategy Platform | {{ result.end_time }}</p>
        </footer>
    </div>
</body>
</html>
        """
        return Template(template_str)
