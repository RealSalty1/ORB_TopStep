"""ID generation utilities."""

from datetime import datetime
from uuid import uuid4


def generate_run_id() -> str:
    """Generate unique run ID.

    Returns:
        Run ID string (timestamp + UUID).
    """
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    uid = str(uuid4())[:8]
    return f"{timestamp}_{uid}"


def generate_trade_id(symbol: str, timestamp: datetime) -> str:
    """Generate trade ID.

    Args:
        symbol: Instrument symbol.
        timestamp: Entry timestamp.

    Returns:
        Trade ID string.
    """
    ts_str = timestamp.strftime("%Y%m%d_%H%M%S")
    return f"{symbol}_{ts_str}"
