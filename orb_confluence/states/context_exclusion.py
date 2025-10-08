"""Context Exclusion Matrix for filtering low-expectancy setups.

Analyzes historical performance across context dimensions:
- OR width quartile
- Breakout delay bucket
- Volume quality tercile
- Auction state
- Gap type

Prunes contexts with statistically poor performance.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from loguru import logger


@dataclass
class ContextSignature:
    """Multi-dimensional context signature for trade classification."""
    
    # OR characteristics
    or_width_quartile: int  # 1-4 (Q1=narrowest, Q4=widest)
    
    # Timing
    breakout_delay_bucket: str  # "0-10", "10-25", "25-40", ">40" minutes
    
    # Volume
    volume_quality_tercile: int  # 1-3 (1=low, 2=mid, 3=high)
    
    # State
    auction_state: str  # INITIATIVE, BALANCED, etc.
    
    # Gap
    gap_type: str  # FULL_UP, FULL_DOWN, PARTIAL, INSIDE, NO_GAP
    
    def to_tuple(self) -> Tuple:
        """Convert to tuple for hashing/grouping."""
        return (
            self.or_width_quartile,
            self.breakout_delay_bucket,
            self.volume_quality_tercile,
            self.auction_state,
            self.gap_type,
        )
    
    def __hash__(self):
        """Hash for dictionary keys."""
        return hash(self.to_tuple())
    
    def __eq__(self, other):
        """Equality comparison."""
        if not isinstance(other, ContextSignature):
            return False
        return self.to_tuple() == other.to_tuple()
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"Context(OR_Q{self.or_width_quartile}, "
            f"delay={self.breakout_delay_bucket}, "
            f"vol_T{self.volume_quality_tercile}, "
            f"{self.auction_state}, {self.gap_type})"
        )


@dataclass
class ContextCell:
    """Single cell in exclusion matrix with performance metrics."""
    
    signature: ContextSignature
    
    # Sample statistics
    n_trades: int
    n_winners: int
    n_losers: int
    
    # Performance
    expectancy: float  # Average R
    win_rate: float
    avg_winner: float
    avg_loser: float
    
    # Probability metrics
    p_extension_mean: Optional[float] = None
    
    # Statistical significance
    expectancy_stderr: float = 0.0
    expectancy_ci_lower: float = 0.0
    expectancy_ci_upper: float = 0.0
    
    # Exclusion decision
    is_excluded: bool = False
    exclusion_reason: Optional[str] = None
    
    def __repr__(self) -> str:
        """String representation."""
        status = "EXCLUDED" if self.is_excluded else "OK"
        return (
            f"Cell({self.signature}, n={self.n_trades}, "
            f"E={self.expectancy:.3f}R, WR={self.win_rate:.1%}) [{status}]"
        )


class ContextExclusionMatrix:
    """Context-based trade filtering system.
    
    Builds multi-dimensional performance matrix and excludes low-expectancy cells.
    
    Example:
        >>> matrix = ContextExclusionMatrix()
        >>> matrix.fit(trades_df)
        >>> 
        >>> # Check if context should be traded
        >>> signature = matrix.create_signature(
        ...     or_width_norm=0.8,
        ...     breakout_delay=12.5,
        ...     volume_quality=0.75,
        ...     auction_state="INITIATIVE",
        ...     gap_type="NO_GAP"
        ... )
        >>> 
        >>> if not matrix.is_excluded(signature):
        ...     # Take trade
        ...     pass
    """
    
    def __init__(
        self,
        min_trades_per_cell: int = 30,
        expectancy_threshold: float = -0.25,  # Exclude if < global - threshold
        p_extension_threshold: Optional[float] = None,  # Exclude if < global - threshold
        confidence_level: float = 0.95,
    ) -> None:
        """Initialize context exclusion matrix.
        
        Args:
            min_trades_per_cell: Minimum trades required for cell evaluation
            expectancy_threshold: Expectancy delta threshold for exclusion
            p_extension_threshold: P(extension) delta threshold (if used)
            confidence_level: Confidence level for statistical tests
        """
        self.min_trades = min_trades_per_cell
        self.expectancy_threshold = expectancy_threshold
        self.p_threshold = p_extension_threshold
        self.confidence_level = confidence_level
        
        # Matrix data
        self.cells: Dict[ContextSignature, ContextCell] = {}
        self.global_expectancy: Optional[float] = None
        self.global_p_extension: Optional[float] = None
        
        # Quantile thresholds (fitted from data)
        self.width_quartiles: Optional[List[float]] = None
        self.volume_terciles: Optional[List[float]] = None
        
        # Metadata
        self.fit_timestamp: Optional[datetime] = None
        self.total_trades_analyzed: int = 0
    
    def fit(
        self,
        trades_df: pd.DataFrame,
        or_width_norm_col: str = "or_width_norm",
        breakout_delay_col: str = "breakout_delay_minutes",
        volume_quality_col: str = "volume_quality_score",
        auction_state_col: str = "auction_state",
        gap_type_col: str = "gap_type",
        realized_r_col: str = "realized_r",
        p_extension_col: Optional[str] = None,
    ) -> None:
        """Fit exclusion matrix from historical trades.
        
        Args:
            trades_df: DataFrame with trade records
            or_width_norm_col: Column name for OR width (normalized)
            breakout_delay_col: Column name for breakout delay (minutes)
            volume_quality_col: Column name for volume quality score
            auction_state_col: Column name for auction state
            gap_type_col: Column name for gap type
            realized_r_col: Column name for realized R-multiple
            p_extension_col: Optional column for p(extension)
        """
        logger.info(f"Fitting context exclusion matrix on {len(trades_df)} trades")
        
        self.total_trades_analyzed = len(trades_df)
        self.fit_timestamp = datetime.now()
        
        # Compute global metrics
        self.global_expectancy = trades_df[realized_r_col].mean()
        if p_extension_col and p_extension_col in trades_df.columns:
            self.global_p_extension = trades_df[p_extension_col].mean()
        
        logger.info(f"Global expectancy: {self.global_expectancy:.3f}R")
        
        # Compute quantile thresholds
        self.width_quartiles = [
            trades_df[or_width_norm_col].quantile(q)
            for q in [0.25, 0.5, 0.75]
        ]
        self.volume_terciles = [
            trades_df[volume_quality_col].quantile(q)
            for q in [0.33, 0.67]
        ]
        
        # Create signatures for all trades
        trades_df = trades_df.copy()
        trades_df["context_signature"] = trades_df.apply(
            lambda row: self.create_signature(
                or_width_norm=row[or_width_norm_col],
                breakout_delay=row[breakout_delay_col],
                volume_quality=row[volume_quality_col],
                auction_state=row[auction_state_col],
                gap_type=row[gap_type_col],
            ),
            axis=1,
        )
        
        # Group by context and compute metrics
        grouped = trades_df.groupby("context_signature")
        
        for signature, group in grouped:
            cell = self._compute_cell_metrics(
                signature=signature,
                group=group,
                realized_r_col=realized_r_col,
                p_extension_col=p_extension_col,
            )
            self.cells[signature] = cell
        
        # Apply exclusion rules
        self._apply_exclusion_rules()
        
        # Summary
        n_excluded = sum(1 for cell in self.cells.values() if cell.is_excluded)
        logger.info(
            f"Context matrix: {len(self.cells)} cells, {n_excluded} excluded "
            f"({n_excluded/len(self.cells)*100:.1f}%)"
        )
    
    def create_signature(
        self,
        or_width_norm: float,
        breakout_delay: float,
        volume_quality: float,
        auction_state: str,
        gap_type: str,
    ) -> ContextSignature:
        """Create context signature from trade features.
        
        Args:
            or_width_norm: OR width / ATR
            breakout_delay: Minutes from OR end
            volume_quality: Volume quality score 0-1
            auction_state: Auction state string
            gap_type: Gap type string
            
        Returns:
            ContextSignature
        """
        # OR width quartile
        if self.width_quartiles is None:
            or_quartile = 2  # Default to middle
        else:
            if or_width_norm <= self.width_quartiles[0]:
                or_quartile = 1
            elif or_width_norm <= self.width_quartiles[1]:
                or_quartile = 2
            elif or_width_norm <= self.width_quartiles[2]:
                or_quartile = 3
            else:
                or_quartile = 4
        
        # Breakout delay bucket
        if breakout_delay <= 10:
            delay_bucket = "0-10"
        elif breakout_delay <= 25:
            delay_bucket = "10-25"
        elif breakout_delay <= 40:
            delay_bucket = "25-40"
        else:
            delay_bucket = ">40"
        
        # Volume quality tercile
        if self.volume_terciles is None:
            vol_tercile = 2  # Default to middle
        else:
            if volume_quality <= self.volume_terciles[0]:
                vol_tercile = 1
            elif volume_quality <= self.volume_terciles[1]:
                vol_tercile = 2
            else:
                vol_tercile = 3
        
        return ContextSignature(
            or_width_quartile=or_quartile,
            breakout_delay_bucket=delay_bucket,
            volume_quality_tercile=vol_tercile,
            auction_state=auction_state,
            gap_type=gap_type,
        )
    
    def is_excluded(self, signature: ContextSignature) -> bool:
        """Check if context should be excluded.
        
        Args:
            signature: Context signature
            
        Returns:
            True if excluded, False if tradeable
        """
        if signature not in self.cells:
            # Unknown context - apply conservative rule
            logger.warning(f"Unknown context: {signature}, defaulting to not excluded")
            return False
        
        return self.cells[signature].is_excluded
    
    def get_cell(self, signature: ContextSignature) -> Optional[ContextCell]:
        """Get cell metrics for signature.
        
        Args:
            signature: Context signature
            
        Returns:
            ContextCell if exists, None otherwise
        """
        return self.cells.get(signature)
    
    def get_exclusion_reason(self, signature: ContextSignature) -> Optional[str]:
        """Get exclusion reason for signature.
        
        Args:
            signature: Context signature
            
        Returns:
            Exclusion reason string if excluded, None otherwise
        """
        cell = self.get_cell(signature)
        if cell and cell.is_excluded:
            return cell.exclusion_reason
        return None
    
    def _compute_cell_metrics(
        self,
        signature: ContextSignature,
        group: pd.DataFrame,
        realized_r_col: str,
        p_extension_col: Optional[str],
    ) -> ContextCell:
        """Compute metrics for a context cell.
        
        Args:
            signature: Context signature
            group: DataFrame of trades in this context
            realized_r_col: Column name for realized R
            p_extension_col: Optional column for p(extension)
            
        Returns:
            ContextCell with computed metrics
        """
        r_values = group[realized_r_col].values
        n_trades = len(r_values)
        n_winners = (r_values > 0).sum()
        n_losers = (r_values < 0).sum()
        
        expectancy = float(np.mean(r_values))
        win_rate = n_winners / n_trades if n_trades > 0 else 0.0
        avg_winner = float(np.mean(r_values[r_values > 0])) if n_winners > 0 else 0.0
        avg_loser = float(np.mean(r_values[r_values < 0])) if n_losers > 0 else 0.0
        
        # Standard error and CI
        stderr = float(np.std(r_values, ddof=1) / np.sqrt(n_trades)) if n_trades > 1 else 0.0
        z_score = 1.96  # 95% CI
        ci_lower = expectancy - z_score * stderr
        ci_upper = expectancy + z_score * stderr
        
        # P(extension) if available
        p_ext_mean = None
        if p_extension_col and p_extension_col in group.columns:
            p_ext_mean = float(group[p_extension_col].mean())
        
        return ContextCell(
            signature=signature,
            n_trades=n_trades,
            n_winners=n_winners,
            n_losers=n_losers,
            expectancy=expectancy,
            win_rate=win_rate,
            avg_winner=avg_winner,
            avg_loser=avg_loser,
            p_extension_mean=p_ext_mean,
            expectancy_stderr=stderr,
            expectancy_ci_lower=ci_lower,
            expectancy_ci_upper=ci_upper,
        )
    
    def _apply_exclusion_rules(self) -> None:
        """Apply exclusion rules to all cells."""
        for signature, cell in self.cells.items():
            # Rule 1: Insufficient data
            if cell.n_trades < self.min_trades:
                continue  # Don't exclude based on insufficient data
            
            # Rule 2: Expectancy significantly below global
            expectancy_delta = cell.expectancy - self.global_expectancy
            if expectancy_delta < self.expectancy_threshold:
                cell.is_excluded = True
                cell.exclusion_reason = (
                    f"Expectancy {cell.expectancy:.3f}R is {expectancy_delta:.3f}R "
                    f"below global {self.global_expectancy:.3f}R"
                )
                continue
            
            # Rule 3: P(extension) significantly below global (if available)
            if (
                self.p_threshold is not None
                and self.global_p_extension is not None
                and cell.p_extension_mean is not None
            ):
                p_delta = cell.p_extension_mean - self.global_p_extension
                if p_delta < -self.p_threshold:
                    cell.is_excluded = True
                    cell.exclusion_reason = (
                        f"P(ext) {cell.p_extension_mean:.3f} is {-p_delta:.3f} "
                        f"below global {self.global_p_extension:.3f}"
                    )
    
    def to_dataframe(self) -> pd.DataFrame:
        """Export matrix to DataFrame for analysis.
        
        Returns:
            DataFrame with all cells and metrics
        """
        records = []
        for cell in self.cells.values():
            record = {
                "or_width_quartile": cell.signature.or_width_quartile,
                "breakout_delay_bucket": cell.signature.breakout_delay_bucket,
                "volume_quality_tercile": cell.signature.volume_quality_tercile,
                "auction_state": cell.signature.auction_state,
                "gap_type": cell.signature.gap_type,
                "n_trades": cell.n_trades,
                "win_rate": cell.win_rate,
                "expectancy": cell.expectancy,
                "avg_winner": cell.avg_winner,
                "avg_loser": cell.avg_loser,
                "expectancy_ci_lower": cell.expectancy_ci_lower,
                "expectancy_ci_upper": cell.expectancy_ci_upper,
                "is_excluded": cell.is_excluded,
                "exclusion_reason": cell.exclusion_reason,
            }
            records.append(record)
        
        df = pd.DataFrame(records)
        df = df.sort_values("expectancy", ascending=False)
        
        return df
    
    def save(self, path: str) -> None:
        """Save matrix to CSV.
        
        Args:
            path: Output CSV path
        """
        df = self.to_dataframe()
        df.to_csv(path, index=False)
        logger.info(f"Saved context exclusion matrix to {path}")

