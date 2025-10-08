"""Fill model for backtest simulation."""


class FillModel:
    """Simulates order fills in backtest."""

    def __init__(self, conservative: bool = True) -> None:
        """Initialize fill model.

        Args:
            conservative: If True, assume stop hit before target if both in same bar.
        """
        self.conservative = conservative

    def check_stop_hit(self, bar: dict, stop_price: float, direction: str) -> bool:
        """Check if stop was hit in bar.

        Args:
            bar: Bar dict with high, low.
            stop_price: Stop price.
            direction: Trade direction.

        Returns:
            True if stop hit.
        """
        # TODO: Add more sophisticated fill logic
        if direction == "long":
            return bar["low"] <= stop_price
        else:
            return bar["high"] >= stop_price

    def check_target_hit(self, bar: dict, target_price: float, direction: str) -> bool:
        """Check if target was hit in bar."""
        if direction == "long":
            return bar["high"] >= target_price
        else:
            return bar["low"] <= target_price
