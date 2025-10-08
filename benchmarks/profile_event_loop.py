"""Profile and benchmark event loop performance.

Identifies hotspots in the backtest engine and provides timing comparisons.

Usage:
    python benchmarks/profile_event_loop.py
"""

import cProfile
import pstats
import time
from io import StringIO
from pathlib import Path

import pandas as pd

from orb_confluence.config import load_config
from orb_confluence.data.sources.synthetic import generate_synthetic_day
from orb_confluence.backtest.event_loop import EventLoopBacktest


def generate_large_dataset(n_days: int = 60, bars_per_day: int = 390) -> pd.DataFrame:
    """Generate large synthetic dataset for profiling.
    
    Args:
        n_days: Number of trading days to generate.
        bars_per_day: Bars per day (default 390 = 6.5 hours * 60 min).
        
    Returns:
        DataFrame with all bars concatenated.
    """
    print(f"Generating {n_days} days × {bars_per_day} bars = {n_days * bars_per_day:,} total bars...")
    
    all_bars = []
    
    for day_num in range(n_days):
        day_bars = generate_synthetic_day(
            seed=day_num,
            regime='trend_up' if day_num % 3 == 0 else 'mean_revert',
            minutes=bars_per_day,
            base_price=100.0 + day_num * 0.5,  # Slight drift
            volatility_mult=1.0,
            vol_profile='u_shape'
        )
        all_bars.append(day_bars)
    
    bars_df = pd.concat(all_bars, ignore_index=True)
    print(f"Generated {len(bars_df):,} bars")
    
    return bars_df


def benchmark_baseline(config, bars_df: pd.DataFrame) -> float:
    """Benchmark baseline performance.
    
    Args:
        config: Strategy configuration.
        bars_df: Bars to backtest.
        
    Returns:
        Elapsed time in seconds.
    """
    print("\n" + "="*60)
    print("BASELINE BENCHMARK")
    print("="*60)
    
    engine = EventLoopBacktest(config)
    
    start = time.time()
    result = engine.run(bars_df)
    elapsed = time.time() - start
    
    print(f"Elapsed: {elapsed:.3f}s")
    print(f"Bars processed: {len(bars_df):,}")
    print(f"Bars/second: {len(bars_df)/elapsed:,.0f}")
    print(f"Trades generated: {len(result.trades)}")
    
    return elapsed


def profile_event_loop(config, bars_df: pd.DataFrame, output_file: str = "profile_stats.txt"):
    """Profile event loop with cProfile.
    
    Args:
        config: Strategy configuration.
        bars_df: Bars to backtest.
        output_file: Output file for profile stats.
    """
    print("\n" + "="*60)
    print("PROFILING EVENT LOOP")
    print("="*60)
    
    engine = EventLoopBacktest(config)
    
    # Profile execution
    profiler = cProfile.Profile()
    profiler.enable()
    
    result = engine.run(bars_df)
    
    profiler.disable()
    
    # Generate stats
    stream = StringIO()
    stats = pstats.Stats(profiler, stream=stream)
    stats.strip_dirs()
    stats.sort_stats('cumulative')
    
    print("\nTop 20 functions by cumulative time:")
    print("-" * 60)
    stats.print_stats(20)
    
    # Print to console
    print(stream.getvalue())
    
    # Also save to file
    with open(output_file, 'w') as f:
        stats = pstats.Stats(profiler, stream=f)
        stats.strip_dirs()
        stats.sort_stats('cumulative')
        stats.print_stats(50)
    
    print(f"\nFull profile saved to: {output_file}")
    
    # Identify hotspots
    print("\n" + "="*60)
    print("HOTSPOT ANALYSIS")
    print("="*60)
    
    stats = pstats.Stats(profiler)
    stats.strip_dirs()
    stats.sort_stats('cumulative')
    
    # Get top functions
    stats_list = []
    for func, (cc, nc, tt, ct, callers) in stats.stats.items():
        filename, line, func_name = func
        stats_list.append({
            'function': func_name,
            'file': filename,
            'cumtime': ct,
            'ncalls': nc,
        })
    
    stats_df = pd.DataFrame(stats_list)
    stats_df = stats_df.sort_values('cumtime', ascending=False).head(20)
    
    print("\nTop 20 functions by cumulative time:")
    print(stats_df.to_string(index=False))
    
    # Identify likely hotspots
    print("\n" + "="*60)
    print("IDENTIFIED HOTSPOTS (likely candidates for optimization):")
    print("="*60)
    
    hotspot_keywords = ['adx', 'update', 'analyze_price_action', 'detect', 'compute']
    hotspots = stats_df[stats_df['function'].str.lower().str.contains('|'.join(hotspot_keywords), na=False)]
    
    if len(hotspots) > 0:
        print(hotspots.head(10).to_string(index=False))
    
    return result


def main():
    """Main benchmark and profiling routine."""
    print("="*60)
    print("ORB CONFLUENCE - PERFORMANCE PROFILING")
    print("="*60)
    
    # Load config
    config = load_config()
    
    # Generate large dataset (60 days × 390 bars = 23,400 bars)
    bars_df = generate_large_dataset(n_days=60, bars_per_day=390)
    
    # Baseline benchmark
    baseline_time = benchmark_baseline(config, bars_df)
    
    # Profile to identify hotspots
    result = profile_event_loop(config, bars_df, output_file="profile_baseline.txt")
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Total bars: {len(bars_df):,}")
    print(f"Total time: {baseline_time:.3f}s")
    print(f"Throughput: {len(bars_df)/baseline_time:,.0f} bars/second")
    print(f"Trades: {len(result.trades)}")
    print("\nLikely hotspots for optimization:")
    print("  1. ADX calculation (Wilder's smoothing in loop)")
    print("  2. Price action pivot detection (rolling window)")
    print("  3. Loop overhead (per-bar state updates)")
    print("\nOptimization strategies:")
    print("  • Vectorize ADX calculation (batch mode)")
    print("  • Use numba @njit for tight loops")
    print("  • Pre-compute factors where possible")


if __name__ == "__main__":
    main()
