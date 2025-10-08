"""Factor attribution analysis.

Analyzes contribution of individual factors to trade outcomes.
"""

from dataclasses import dataclass
from typing import Dict, List

import pandas as pd

from ..strategy.trade_state import ActiveTrade


@dataclass
class FactorAttribution:
    """Factor attribution analysis results.
    
    Attributes:
        factor_presence: DataFrame with factor presence vs outcome
        score_buckets: DataFrame with score bucket performance
        factor_win_rates: Dict of factor-specific win rates
        factor_avg_r: Dict of factor-specific average R
    """
    
    factor_presence: pd.DataFrame
    score_buckets: pd.DataFrame
    factor_win_rates: Dict[str, float]
    factor_avg_r: Dict[str, float]


def analyze_factor_attribution(trades: List[ActiveTrade]) -> FactorAttribution:
    """Analyze factor contribution to trade outcomes.
    
    Creates pivot tables showing:
    - Win rate when factor present vs absent
    - Average R when factor present vs absent
    - Overall factor statistics
    
    Args:
        trades: List of completed trades with signals.
        
    Returns:
        FactorAttribution with analysis DataFrames.
        
    Examples:
        >>> attr = analyze_factor_attribution(trades)
        >>> print(attr.factor_win_rates)
        {'rel_vol': 0.65, 'price_action': 0.58, ...}
    """
    if not trades:
        return FactorAttribution(
            factor_presence=pd.DataFrame(),
            score_buckets=pd.DataFrame(),
            factor_win_rates={},
            factor_avg_r={},
        )
    
    # Extract factor data from trades
    records = []
    for trade in trades:
        if trade.signal is None or not trade.signal.factors:
            continue
        
        record = {
            'trade_id': trade.trade_id,
            'realized_r': trade.realized_r,
            'win': trade.realized_r > 0 if trade.realized_r else False,
            'confluence_score': trade.signal.confluence_score,
        }
        
        # Add factor flags
        for factor_name, factor_value in trade.signal.factors.items():
            record[f'factor_{factor_name}'] = factor_value > 0.5
        
        records.append(record)
    
    if not records:
        return FactorAttribution(
            factor_presence=pd.DataFrame(),
            score_buckets=pd.DataFrame(),
            factor_win_rates={},
            factor_avg_r={},
        )
    
    df = pd.DataFrame(records)
    
    # Identify factor columns
    factor_cols = [col for col in df.columns if col.startswith('factor_')]
    
    # Build factor presence pivot
    factor_presence_records = []
    
    for factor_col in factor_cols:
        factor_name = factor_col.replace('factor_', '')
        
        # Present
        present = df[df[factor_col]]
        present_win_rate = present['win'].mean() if len(present) > 0 else 0.0
        present_avg_r = present['realized_r'].mean() if len(present) > 0 else 0.0
        present_count = len(present)
        
        # Absent
        absent = df[~df[factor_col]]
        absent_win_rate = absent['win'].mean() if len(absent) > 0 else 0.0
        absent_avg_r = absent['realized_r'].mean() if len(absent) > 0 else 0.0
        absent_count = len(absent)
        
        factor_presence_records.append({
            'factor': factor_name,
            'present_count': present_count,
            'present_win_rate': present_win_rate,
            'present_avg_r': present_avg_r,
            'absent_count': absent_count,
            'absent_win_rate': absent_win_rate,
            'absent_avg_r': absent_avg_r,
            'delta_win_rate': present_win_rate - absent_win_rate,
            'delta_avg_r': present_avg_r - absent_avg_r,
        })
    
    factor_presence_df = pd.DataFrame(factor_presence_records)
    
    # Factor-specific statistics
    factor_win_rates = {}
    factor_avg_r = {}
    
    for factor_col in factor_cols:
        factor_name = factor_col.replace('factor_', '')
        present = df[df[factor_col]]
        
        factor_win_rates[factor_name] = present['win'].mean() if len(present) > 0 else 0.0
        factor_avg_r[factor_name] = present['realized_r'].mean() if len(present) > 0 else 0.0
    
    return FactorAttribution(
        factor_presence=factor_presence_df,
        score_buckets=pd.DataFrame(),  # Will be filled by score analysis
        factor_win_rates=factor_win_rates,
        factor_avg_r=factor_avg_r,
    )


def analyze_score_buckets(
    trades: List[ActiveTrade],
    bucket_size: float = 0.5,
) -> pd.DataFrame:
    """Analyze performance by confluence score buckets.
    
    Groups trades by score ranges and computes performance metrics.
    
    Args:
        trades: List of completed trades with signals.
        bucket_size: Score bucket size (e.g., 0.5 for 0-0.5, 0.5-1.0, etc.).
        
    Returns:
        DataFrame with columns: score_bucket, count, win_rate, avg_r.
        
    Examples:
        >>> score_df = analyze_score_buckets(trades, bucket_size=0.5)
        >>> print(score_df)
           score_bucket  count  win_rate  avg_r
        0      0.0-0.5      5      0.40   -0.2
        1      0.5-1.0     10      0.50    0.1
        2      1.0-1.5     20      0.60    0.3
        3      1.5-2.0     15      0.70    0.5
    """
    if not trades:
        return pd.DataFrame(columns=['score_bucket', 'count', 'win_rate', 'avg_r'])
    
    # Extract score and outcome
    records = []
    for trade in trades:
        if trade.signal is None:
            continue
        
        records.append({
            'score': trade.signal.confluence_score,
            'realized_r': trade.realized_r,
            'win': trade.realized_r > 0 if trade.realized_r else False,
        })
    
    if not records:
        return pd.DataFrame(columns=['score_bucket', 'count', 'win_rate', 'avg_r'])
    
    df = pd.DataFrame(records)
    
    # Create buckets
    min_score = df['score'].min()
    max_score = df['score'].max()
    
    # Round down to bucket_size
    min_bucket = int(min_score / bucket_size) * bucket_size
    max_bucket = (int(max_score / bucket_size) + 1) * bucket_size
    
    bins = []
    current = min_bucket
    while current < max_bucket:
        bins.append(current)
        current += bucket_size
    bins.append(max_bucket)
    
    # Bucket labels
    labels = [f"{bins[i]:.1f}-{bins[i+1]:.1f}" for i in range(len(bins) - 1)]
    
    df['score_bucket'] = pd.cut(
        df['score'],
        bins=bins,
        labels=labels,
        include_lowest=True,
    )
    
    # Group by bucket
    bucket_stats = df.groupby('score_bucket', observed=True).agg({
        'score': 'count',
        'win': 'mean',
        'realized_r': 'mean',
    }).reset_index()
    
    bucket_stats.columns = ['score_bucket', 'count', 'win_rate', 'avg_r']
    
    return bucket_stats