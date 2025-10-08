"""Report generation."""

from pathlib import Path

from jinja2 import Template


def generate_report(results: dict, output_path: Path) -> None:
    """Generate HTML backtest report.

    Args:
        results: Backtest results dict.
        output_path: Path to save HTML report.
    """
    # TODO: Implement HTML report with charts
    template_str = """
<!DOCTYPE html>
<html>
<head>
    <title>ORB Strategy Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        h1 { color: #333; }
        .metric { margin: 10px 0; }
    </style>
</head>
<body>
    <h1>ORB Strategy Backtest Report</h1>
    <div class="metric">Total Trades: {{ total_trades }}</div>
    <div class="metric">Win Rate: {{ win_rate }}%</div>
    <div class="metric">Avg R: {{ avg_r }}</div>
</body>
</html>
    """

    template = Template(template_str)
    html = template.render(**results)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html)
