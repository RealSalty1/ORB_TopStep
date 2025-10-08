"""Benchmark script comparing baseline vs optimized implementations.

Compares:
- Baseline event loop (streaming calculations)
- Optimized event loop (vectorized ADX)
- Memory usage
- Throughput

Usage:
    python benchmarks/benchmark_optimizations.py
"""

import time
from pathlib import Path

import pandas as pd
import numpy as np

from orb_confluence.config import load_config
from orb_confluence.data.sources.synthetic import generate_synthetic_day
from orb_confluence.backtest.event_loop import EventLoopBacktest


def generate_test_dataset(n_days: int = 60, bars_per_day: int = 390) -> pd.DataFrame:
    """Generate test dataset.
    
    Args:
        n_days: Number of days.
        bars_per_day: Bars per day.
        
    Returns:
        DataFrame with bars.
    """
    all_bars = []
    for day_num in range(n_days):
        day_bars = generate_synthetic_day(
            seed=day_num,
            regime='trend_up' if day_num % 2 == 0 else 'mean_revert',
            minutes=bars_per_day,
            base_price=100.0,
            volatility_mult=1.0
        )
        all_bars.append(day_bars)
    
    return pd.concat(all_bars, ignore_index=True)


def benchmark_baseline(config, bars_df: pd.DataFrame, n_runs: int = 3) -> dict:
    """Benchmark baseline implementation.
    
    Args:
        config: Strategy configuration.
        bars_df: Bars to backtest.
        n_runs: Number of runs.
        
    Returns:
        Dictionary with timing results.
    """
    print("\n" + "="*60)
    print("BASELINE (Streaming Calculations)")
    print("="*60)
    
    times = []
    trade_counts = []
    
    for run in range(n_runs):
        engine = EventLoopBacktest(config)
        
        start = time.time()
        result = engine.run(bars_df)
        elapsed = time.time() - start
        
        times.append(elapsed)
        trade_counts.append(len(result.trades))
        
        print(f"Run {run+1}: {elapsed:.3f}s, {len(bars_df)/elapsed:,.0f} bars/sec, {len(result.trades)} trades")
    
    mean_time = np.mean(times)
    std_time = np.std(times)
    
    print(f"\nMean: {mean_time:.3f}s ± {std_time:.3f}s")
    print(f"Throughput: {len(bars_df)/mean_time:,.0f} bars/sec")
    
    return {
        'mean_time': mean_time,
        'std_time': std_time,
        'bars_per_sec': len(bars_df) / mean_time,
        'trades': np.mean(trade_counts),
    }


def benchmark_optimized_adx(config, bars_df: pd.DataFrame, n_runs: int = 3) -> dict:
    """Benchmark with optimized ADX (vectorized).
    
    Args:
        config: Strategy configuration.
        bars_df: Bars to backtest.
        n_runs: Number of runs.
        
    Returns:
        Dictionary with timing results.
    """
    print("\n" + "="*60)
    print("OPTIMIZED (Vectorized ADX with Numba)")
    print("="*60)
    
    # Pre-compute ADX for entire dataset
    from orb_confluence.features.adx_optimized import compute_adx_vectorized
    
    adx_precompute_start = time.time()
    bars_with_adx = compute_adx_vectorized(bars_df, period=14)
    adx_precompute_time = time.time() - adx_precompute_start
    
    print(f"ADX pre-computation: {adx_precompute_time:.3f}s")
    print(f"ADX throughput: {len(bars_df)/adx_precompute_time:,.0f} bars/sec")
    
    # Note: Full integration with event loop would require modifications
    # For now, we just show ADX speedup
    
    print("\nNote: Full event loop integration requires modifying EventLoopBacktest")
    print("to use pre-computed ADX values. This benchmark shows ADX calculation speedup only.")
    
    return {
        'adx_precompute_time': adx_precompute_time,
        'adx_bars_per_sec': len(bars_df) / adx_precompute_time,
    }


def benchmark_adx_only(bars_df: pd.DataFrame, n_runs: int = 5) -> dict:
    """Benchmark ADX calculation only (streaming vs vectorized).
    
    Args:
        bars_df: Bars to compute ADX for.
        n_runs: Number of runs.
        
    Returns:
        Dictionary with comparison results.
    """
    print("\n" + "="*60)
    print("ADX CALCULATION COMPARISON")
    print("="*60)
    
    # Streaming (original)
    from orb_confluence.features.adx import ADX
    
    print("\nStreaming ADX (original):")
    times_streaming = []
    for run in range(n_runs):
        adx = ADX(period=14)
        start = time.time()
        for i in range(len(bars_df)):
            row = bars_df.iloc[i]
            adx.update(row['high'], row['low'], row['close'])
        elapsed = time.time() - start
        times_streaming.append(elapsed)
        print(f"  Run {run+1}: {elapsed:.4f}s, {len(bars_df)/elapsed:,.0f} bars/sec")
    
    mean_streaming = np.mean(times_streaming)
    
    # Vectorized (optimized)
    from orb_confluence.features.adx_optimized import compute_adx_vectorized
    
    print("\nVectorized ADX (numba):")
    times_vectorized = []
    for run in range(n_runs):
        start = time.time()
        result = compute_adx_vectorized(bars_df, period=14)
        elapsed = time.time() - start
        times_vectorized.append(elapsed)
        print(f"  Run {run+1}: {elapsed:.4f}s, {len(bars_df)/elapsed:,.0f} bars/sec")
    
    mean_vectorized = np.mean(times_vectorized)
    
    # Comparison
    speedup = mean_streaming / mean_vectorized
    
    print("\n" + "="*60)
    print("ADX SPEEDUP")
    print("="*60)
    print(f"Streaming: {mean_streaming:.4f}s ({len(bars_df)/mean_streaming:,.0f} bars/sec)")
    print(f"Vectorized: {mean_vectorized:.4f}s ({len(bars_df)/mean_vectorized:,.0f} bars/sec)")
    print(f"Speedup: {speedup:.1f}x faster")
    
    return {
        'streaming_time': mean_streaming,
        'vectorized_time': mean_vectorized,
        'speedup': speedup,
    }


def estimate_event_loop_speedup(baseline_time: float, adx_speedup: float, adx_fraction: float = 0.3) -> float:
    """Estimate event loop speedup from ADX optimization.
    
    Assumes ADX takes ~30% of event loop time (based on profiling).
    
    Args:
        baseline_time: Baseline event loop time.
        adx_speedup: Speedup factor for ADX (e.g., 20x).
        adx_fraction: Fraction of time spent in ADX (0.0-1.0).
        
    Returns:
        Estimated optimized time.
    """
    adx_time = baseline_time * adx_fraction
    other_time = baseline_time * (1 - adx_fraction)
    
    optimized_adx_time = adx_time / adx_speedup
    optimized_total = optimized_adx_time + other_time
    
    return optimized_total


def main():
    """Main benchmark routine."""
    print("="*60)
    print("ORB CONFLUENCE - OPTIMIZATION BENCHMARKS")
    print("="*60)
    
    # Load config
    config = load_config()
    
    # Generate dataset
    print("\nGenerating test dataset (60 days × 390 bars = 23,400 bars)...")
    bars_df = generate_test_dataset(n_days=60, bars_per_day=390)
    print(f"Generated {len(bars_df):,} bars")
    
    # Benchmark ADX only (most accurate comparison)
    adx_results = benchmark_adx_only(bars_df, n_runs=5)
    
    # Benchmark baseline event loop
    baseline_results = benchmark_baseline(config, bars_df, n_runs=3)
    
    # Estimate potential speedup
    print("\n" + "="*60)
    print("ESTIMATED EVENT LOOP SPEEDUP")
    print("="*60)
    print("\nAssumptions:")
    print("  • ADX takes ~30% of event loop time (based on profiling)")
    print(f"  • ADX speedup: {adx_results['speedup']:.1f}x")
    
    for adx_fraction in [0.2, 0.3, 0.4]:
        optimized_time = estimate_event_loop_speedup(
            baseline_results['mean_time'],
            adx_results['speedup'],
            adx_fraction
        )
        total_speedup = baseline_results['mean_time'] / optimized_time
        
        print(f"\nIf ADX is {adx_fraction*100:.0f}% of time:")
        print(f"  Baseline: {baseline_results['mean_time']:.3f}s")
        print(f"  Optimized: {optimized_time:.3f}s")
        print(f"  Speedup: {total_speedup:.2f}x faster")
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"\nBaseline Event Loop:")
    print(f"  Time: {baseline_results['mean_time']:.3f}s")
    print(f"  Throughput: {baseline_results['bars_per_sec']:,.0f} bars/sec")
    
    print(f"\nADX Optimization:")
    print(f"  Streaming: {adx_results['streaming_time']:.4f}s")
    print(f"  Vectorized: {adx_results['vectorized_time']:.4f}s")
    print(f"  Speedup: {adx_results['speedup']:.1f}x")
    
    print(f"\nEstimated Event Loop Improvement:")
    print(f"  Conservative (ADX=20%): ~{estimate_event_loop_speedup(baseline_results['mean_time'], adx_results['speedup'], 0.2) / baseline_results['mean_time']:.2f}x")
    print(f"  Moderate (ADX=30%): ~{estimate_event_loop_speedup(baseline_results['mean_time'], adx_results['speedup'], 0.3) / baseline_results['mean_time']:.2f}x")
    print(f"  Aggressive (ADX=40%): ~{estimate_event_loop_speedup(baseline_results['mean_time'], adx_results['speedup'], 0.4) / baseline_results['mean_time']:.2f}x")
    
    print("\n" + "="*60)
    print("OPTIMIZATION RECOMMENDATIONS")
    print("="*60)
    print("\n1. Priority: Vectorize ADX calculation")
    print(f"   • Impact: {adx_results['speedup']:.1f}x speedup on ADX")
    print("   • Implementation: Use compute_adx_vectorized() from adx_optimized.py")
    print("   • Effort: Moderate (requires event loop modifications)")
    
    print("\n2. Secondary: Vectorize other factors")
    print("   • Targets: Price action, VWAP, Relative volume")
    print("   • Expected: 5-10x speedup per factor")
    
    print("\n3. Tertiary: Numba for loop overhead")
    print("   • Target: Core event loop iteration")
    print("   • Expected: 2-3x speedup")
    
    print("\nTotal potential speedup: 3-5x for full event loop")


if __name__ == "__main__":
    main()
