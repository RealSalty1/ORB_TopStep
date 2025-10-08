"""HTML report generation using Jinja2 templates.

Generates comprehensive backtest reports with charts and statistics.
"""

import base64
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import List, Optional

import pandas as pd
from jinja2 import Template

from .analytics.metrics import PerformanceMetrics, compute_metrics
from .analytics.attribution import FactorAttribution, analyze_factor_attribution, analyze_score_buckets
from .backtest.event_loop import BacktestResult
from .config.schema import StrategyConfig
from .strategy.trade_state import ActiveTrade


# HTML Template
REPORT_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ORB Confluence Strategy - Backtest Report</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 {
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }
        h2 {
            color: #34495e;
            margin-top: 30px;
            border-bottom: 2px solid #ecf0f1;
            padding-bottom: 8px;
        }
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }
        .metric-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .metric-card.positive {
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
        }
        .metric-card.negative {
            background: linear-gradient(135deg, #ee0979 0%, #ff6a00 100%);
        }
        .metric-label {
            font-size: 14px;
            opacity: 0.9;
            margin-bottom: 8px;
        }
        .metric-value {
            font-size: 28px;
            font-weight: bold;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th {
            background-color: #3498db;
            color: white;
            font-weight: bold;
        }
        tr:hover {
            background-color: #f5f5f5;
        }
        .chart-container {
            margin: 20px 0;
            text-align: center;
        }
        .chart-container img {
            max-width: 100%;
            height: auto;
            border: 1px solid #ddd;
            border-radius: 4px;
        }
        .config-section {
            background-color: #ecf0f1;
            padding: 15px;
            border-radius: 4px;
            font-family: monospace;
            font-size: 13px;
            margin: 20px 0;
        }
        .timestamp {
            color: #7f8c8d;
            font-size: 14px;
            margin-top: 30px;
            text-align: center;
        }
        .positive-value {
            color: #27ae60;
            font-weight: bold;
        }
        .negative-value {
            color: #e74c3c;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 ORB Confluence Strategy - Backtest Report</h1>
        
        <!-- Summary Metrics -->
        <h2>Performance Summary</h2>
        <div class="metrics-grid">
            <div class="metric-card {% if metrics.total_r > 0 %}positive{% else %}negative{% endif %}">
                <div class="metric-label">Total R</div>
                <div class="metric-value">{{ "%.2f"|format(metrics.total_r) }}R</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Win Rate</div>
                <div class="metric-value">{{ "%.1f"|format(metrics.win_rate * 100) }}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Total Trades</div>
                <div class="metric-value">{{ metrics.total_trades }}</div>
            </div>
            <div class="metric-card {% if metrics.sharpe_ratio > 1 %}positive{% endif %}">
                <div class="metric-label">Sharpe Ratio</div>
                <div class="metric-value">{{ "%.2f"|format(metrics.sharpe_ratio) }}</div>
            </div>
            <div class="metric-card {% if metrics.profit_factor > 1.5 %}positive{% endif %}">
                <div class="metric-label">Profit Factor</div>
                <div class="metric-value">{{ "%.2f"|format(metrics.profit_factor) }}</div>
            </div>
            <div class="metric-card negative">
                <div class="metric-label">Max Drawdown</div>
                <div class="metric-value">{{ "%.2f"|format(metrics.max_drawdown_r) }}R</div>
            </div>
        </div>
        
        <!-- Detailed Metrics Table -->
        <h2>Detailed Metrics</h2>
        <table>
            <tr>
                <th>Metric</th>
                <th>Value</th>
            </tr>
            <tr>
                <td>Average R</td>
                <td class="{% if metrics.average_r > 0 %}positive-value{% else %}negative-value{% endif %}">
                    {{ "%.3f"|format(metrics.average_r) }}R
                </td>
            </tr>
            <tr>
                <td>Median R</td>
                <td>{{ "%.3f"|format(metrics.median_r) }}R</td>
            </tr>
            <tr>
                <td>Expectancy</td>
                <td class="{% if metrics.expectancy > 0 %}positive-value{% else %}negative-value{% endif %}">
                    {{ "%.3f"|format(metrics.expectancy) }}R
                </td>
            </tr>
            <tr>
                <td>Sortino Ratio</td>
                <td>{{ "%.2f"|format(metrics.sortino_ratio) }}</td>
            </tr>
            <tr>
                <td>Average Winner</td>
                <td class="positive-value">{{ "%.2f"|format(metrics.avg_winner_r) }}R</td>
            </tr>
            <tr>
                <td>Average Loser</td>
                <td class="negative-value">{{ "%.2f"|format(metrics.avg_loser_r) }}R</td>
            </tr>
            <tr>
                <td>Largest Winner</td>
                <td class="positive-value">{{ "%.2f"|format(metrics.largest_winner_r) }}R</td>
            </tr>
            <tr>
                <td>Largest Loser</td>
                <td class="negative-value">{{ "%.2f"|format(metrics.largest_loser_r) }}R</td>
            </tr>
            <tr>
                <td>Consecutive Wins (Max)</td>
                <td>{{ metrics.consecutive_wins }}</td>
            </tr>
            <tr>
                <td>Consecutive Losses (Max)</td>
                <td>{{ metrics.consecutive_losses }}</td>
            </tr>
            {% if metrics.avg_trade_duration_minutes %}
            <tr>
                <td>Avg Trade Duration</td>
                <td>{{ "%.1f"|format(metrics.avg_trade_duration_minutes) }} minutes</td>
            </tr>
            {% endif %}
        </table>
        
        <!-- Opening Range Stats -->
        {% if or_stats %}
        <h2>Opening Range Statistics</h2>
        <table>
            <tr>
                <th>Metric</th>
                <th>Value</th>
            </tr>
            <tr>
                <td>Total ORs Built</td>
                <td>{{ or_stats.total_ors }}</td>
            </tr>
            <tr>
                <td>Valid ORs</td>
                <td class="positive-value">{{ or_stats.valid_ors }} ({{ "%.1f"|format(or_stats.valid_pct) }}%)</td>
            </tr>
            <tr>
                <td>Invalid ORs</td>
                <td class="negative-value">{{ or_stats.invalid_ors }} ({{ "%.1f"|format(or_stats.invalid_pct) }}%)</td>
            </tr>
        </table>
        {% endif %}
        
        <!-- Factor Attribution -->
        {% if attribution %}
        <h2>Factor Attribution</h2>
        <table>
            <tr>
                <th>Factor</th>
                <th>Present Count</th>
                <th>Win Rate (Present)</th>
                <th>Avg R (Present)</th>
                <th>Win Rate (Absent)</th>
                <th>Avg R (Absent)</th>
                <th>Δ Win Rate</th>
                <th>Δ Avg R</th>
            </tr>
            {% for _, row in attribution.factor_presence.iterrows() %}
            <tr>
                <td><strong>{{ row.factor }}</strong></td>
                <td>{{ row.present_count }}</td>
                <td>{{ "%.1f"|format(row.present_win_rate * 100) }}%</td>
                <td class="{% if row.present_avg_r > 0 %}positive-value{% else %}negative-value{% endif %}">
                    {{ "%.2f"|format(row.present_avg_r) }}R
                </td>
                <td>{{ "%.1f"|format(row.absent_win_rate * 100) }}%</td>
                <td>{{ "%.2f"|format(row.absent_avg_r) }}R</td>
                <td class="{% if row.delta_win_rate > 0 %}positive-value{% else %}negative-value{% endif %}">
                    {{ "%+.1f"|format(row.delta_win_rate * 100) }}%
                </td>
                <td class="{% if row.delta_avg_r > 0 %}positive-value{% else %}negative-value{% endif %}">
                    {{ "%+.2f"|format(row.delta_avg_r) }}R
                </td>
            </tr>
            {% endfor %}
        </table>
        {% endif %}
        
        <!-- Score Buckets -->
        {% if score_buckets is not none and not score_buckets.empty %}
        <h2>Confluence Score Performance</h2>
        <table>
            <tr>
                <th>Score Bucket</th>
                <th>Count</th>
                <th>Win Rate</th>
                <th>Average R</th>
            </tr>
            {% for _, row in score_buckets.iterrows() %}
            <tr>
                <td><strong>{{ row.score_bucket }}</strong></td>
                <td>{{ row['count'] }}</td>
                <td>{{ "%.1f"|format(row.win_rate * 100) }}%</td>
                <td class="{% if row.avg_r > 0 %}positive-value{% else %}negative-value{% endif %}">
                    {{ "%.2f"|format(row.avg_r) }}R
                </td>
            </tr>
            {% endfor %}
        </table>
        {% endif %}
        
        <!-- Charts -->
        {% if charts %}
            {% if charts.r_distribution %}
            <h2>R Distribution</h2>
            <div class="chart-container">
                <img src="data:image/png;base64,{{ charts.r_distribution }}" alt="R Distribution">
            </div>
            {% endif %}
            
            {% if charts.score_gradient %}
            <h2>Score Gradient</h2>
            <div class="chart-container">
                <img src="data:image/png;base64,{{ charts.score_gradient }}" alt="Score Gradient">
            </div>
            {% endif %}
        {% endif %}
        
        <!-- Configuration -->
        <h2>Strategy Configuration</h2>
        <div class="config-section">
            <strong>OR Length:</strong> {{ config.orb.or_length_minutes }} minutes<br>
            <strong>Stop Mode:</strong> {{ config.trade.stop_mode }}<br>
            <strong>Partials:</strong> {{ "Enabled" if config.trade.partials else "Disabled" }}<br>
            {% if config.trade.partials %}
            <strong>Target 1:</strong> {{ config.trade.t1_r }}R ({{ "%.0f"|format(config.trade.t1_pct * 100) }}%)<br>
            <strong>Target 2:</strong> {{ config.trade.t2_r }}R ({{ "%.0f"|format(config.trade.t2_pct * 100) }}%)<br>
            <strong>Runner:</strong> {{ config.trade.runner_r }}R<br>
            {% else %}
            <strong>Target:</strong> {{ config.trade.primary_r }}R<br>
            {% endif %}
            <strong>Max Signals/Day:</strong> {{ config.governance.max_signals_per_day }}<br>
            <strong>Lockout After Losses:</strong> {{ config.governance.lockout_after_losses }}<br>
        </div>
        
        <div class="timestamp">
            Generated: {{ timestamp }}
        </div>
    </div>
</body>
</html>
"""


def generate_report(
    result: BacktestResult,
    config: StrategyConfig,
    output_path: Optional[Path] = None,
    run_id: Optional[str] = None,
) -> str:
    """Generate HTML backtest report.
    
    Args:
        result: Backtest result.
        config: Strategy configuration.
        output_path: Optional output directory (default: ./runs/{run_id}/report.html).
        run_id: Optional run ID (default: timestamp).
        
    Returns:
        HTML string.
        
    Examples:
        >>> html = generate_report(result, config)
        >>> # Save to file
        >>> Path('report.html').write_text(html)
    """
    # Compute metrics
    metrics = compute_metrics(result.trades)
    
    # Compute attribution
    attribution = analyze_factor_attribution(result.trades) if result.trades else None
    
    # Compute score buckets
    score_buckets = analyze_score_buckets(result.trades) if result.trades else pd.DataFrame()
    
    # OR statistics (placeholder - would need actual OR data)
    or_stats = None
    
    # Generate charts (placeholder - would use plotly)
    charts = {}
    
    # Render template
    template = Template(REPORT_TEMPLATE)
    html = template.render(
        metrics=metrics,
        attribution=attribution,
        score_buckets=score_buckets,
        or_stats=or_stats,
        charts=charts,
        config=config,
        timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    )
    
    # Save to file if path provided
    if output_path is not None or run_id is not None:
        if run_id is None:
            run_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        if output_path is None:
            output_path = Path('runs') / run_id / 'report.html'
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html)
    
    return html
