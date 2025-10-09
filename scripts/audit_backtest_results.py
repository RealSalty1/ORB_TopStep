"""
Comprehensive Audit of Backtest Results

This script validates:
1. R-multiple calculations
2. P&L calculations
3. MFE/MAE logic (MAE should be negative, MFE should be positive)
4. Data leakage (future data usage)
5. Trade execution realism
6. Statistical anomalies

Author: Nick Burner
Date: October 9, 2025
"""

import pandas as pd
import numpy as np
from pathlib import Path
import json
from loguru import logger

# Configure logger
logger.add("audit_backtest.log", rotation="10 MB")

# Constants
POINT_VALUE = 50.0  # ES contract
TICK_SIZE = 0.25


def load_backtest_data(run_dir: str):
    """Load all backtest files."""
    run_path = Path(run_dir)
    
    # Load trades
    trades_df = pd.read_csv(run_path / "ES_trades.csv")
    trades_df['entry_time'] = pd.to_datetime(trades_df['entry_time'])
    trades_df['exit_time'] = pd.to_datetime(trades_df['exit_time'])
    
    # Load metrics
    with open(run_path / "metrics.json") as f:
        metrics = json.load(f)
    
    # Load equity
    equity_df = pd.read_csv(run_path / "ES_equity.csv")
    equity_df['timestamp'] = pd.to_datetime(equity_df['timestamp'])
    
    # Load config
    with open(run_path / "config.json") as f:
        config = json.load(f)
    
    logger.info(f"Loaded {len(trades_df)} trades from {run_dir}")
    
    return trades_df, metrics, equity_df, config


def audit_r_multiples(trades_df: pd.DataFrame):
    """Audit R-multiple calculations."""
    logger.info("\n" + "=" * 80)
    logger.info("AUDIT 1: R-MULTIPLE CALCULATIONS")
    logger.info("=" * 80)
    
    issues = []
    
    for idx, trade in trades_df.iterrows():
        entry = trade['entry_price']
        exit = trade['exit_price']
        direction = trade['direction']
        size = trade['size']
        r_multiple = trade['r_multiple']
        pnl = trade['pnl']
        
        # Calculate expected price move
        if direction == 'LONG':
            price_move = exit - entry
        else:
            price_move = entry - exit
        
        # Calculate expected P&L
        expected_pnl = price_move * size * POINT_VALUE
        pnl_error = abs(pnl - expected_pnl)
        
        # Check P&L accuracy (within 1 tick)
        if pnl_error > (TICK_SIZE * size * POINT_VALUE * 2):  # 2 ticks tolerance for slippage
            issues.append({
                'trade_num': idx,
                'type': 'P&L_MISMATCH',
                'expected_pnl': expected_pnl,
                'actual_pnl': pnl,
                'error': pnl_error,
            })
        
        # Validate R-multiple sign
        if r_multiple > 0 and pnl < 0:
            issues.append({
                'trade_num': idx,
                'type': 'R_SIGN_MISMATCH',
                'r_multiple': r_multiple,
                'pnl': pnl,
            })
        
        if r_multiple < 0 and pnl > 0:
            issues.append({
                'trade_num': idx,
                'type': 'R_SIGN_MISMATCH',
                'r_multiple': r_multiple,
                'pnl': pnl,
            })
    
    if issues:
        logger.warning(f"Found {len(issues)} R-multiple/P&L issues:")
        for issue in issues[:10]:  # Show first 10
            logger.warning(f"  {issue}")
    else:
        logger.info("✓ All R-multiple and P&L calculations are accurate")
    
    return issues


def audit_mfe_mae(trades_df: pd.DataFrame):
    """Audit MFE/MAE logic."""
    logger.info("\n" + "=" * 80)
    logger.info("AUDIT 2: MFE/MAE LOGIC")
    logger.info("=" * 80)
    
    issues = []
    
    for idx, trade in trades_df.iterrows():
        mfe = trade['mfe']
        mae = trade['mae']
        r_multiple = trade['r_multiple']
        exit_reason = trade['exit_reason']
        
        # MFE should always be >= 0 (most favorable)
        if mfe < 0:
            issues.append({
                'trade_num': idx,
                'type': 'NEGATIVE_MFE',
                'mfe': mfe,
            })
        
        # MAE should always be <= 0 (most adverse)
        if mae > 0:
            issues.append({
                'trade_num': idx,
                'type': 'POSITIVE_MAE',
                'mae': mae,
            })
        
        # Exit R should be between MAE and MFE
        if r_multiple < mae or r_multiple > mfe:
            issues.append({
                'trade_num': idx,
                'type': 'R_OUT_OF_RANGE',
                'r_multiple': r_multiple,
                'mfe': mfe,
                'mae': mae,
                'exit_reason': exit_reason,
            })
        
        # If stopped out, R should be close to -1.0
        if exit_reason == 'STOP' and r_multiple < 0:
            if r_multiple < -1.2:  # More than 20% worse than expected
                issues.append({
                    'trade_num': idx,
                    'type': 'STOP_SLIPPAGE_HIGH',
                    'r_multiple': r_multiple,
                })
    
    if issues:
        logger.warning(f"Found {len(issues)} MFE/MAE issues:")
        for issue in issues[:10]:
            logger.warning(f"  {issue}")
    else:
        logger.info("✓ All MFE/MAE values are within expected ranges")
    
    return issues


def audit_timing(trades_df: pd.DataFrame):
    """Audit trade timing for data leakage."""
    logger.info("\n" + "=" * 80)
    logger.info("AUDIT 3: TIMING AND DATA LEAKAGE")
    logger.info("=" * 80)
    
    issues = []
    
    for idx, trade in trades_df.iterrows():
        entry_time = trade['entry_time']
        exit_time = trade['exit_time']
        bars_in_trade = trade['bars_in_trade']
        
        # Exit should be after entry
        if exit_time <= entry_time:
            issues.append({
                'trade_num': idx,
                'type': 'EXIT_BEFORE_ENTRY',
                'entry_time': entry_time,
                'exit_time': exit_time,
            })
        
        # Bars in trade should match time difference (approximately)
        time_diff_minutes = (exit_time - entry_time).total_seconds() / 60
        expected_bars = int(time_diff_minutes)
        
        if abs(bars_in_trade - expected_bars) > 2:  # 2 bar tolerance
            issues.append({
                'trade_num': idx,
                'type': 'BARS_MISMATCH',
                'bars_in_trade': bars_in_trade,
                'expected_bars': expected_bars,
                'time_diff_minutes': time_diff_minutes,
            })
    
    # Check for overlapping trades (should only have one position at a time)
    trades_sorted = trades_df.sort_values('entry_time')
    for i in range(len(trades_sorted) - 1):
        current_exit = trades_sorted.iloc[i]['exit_time']
        next_entry = trades_sorted.iloc[i + 1]['entry_time']
        
        if next_entry < current_exit:
            issues.append({
                'trade_num': i,
                'type': 'OVERLAPPING_TRADES',
                'current_exit': current_exit,
                'next_entry': next_entry,
            })
    
    if issues:
        logger.warning(f"Found {len(issues)} timing issues:")
        for issue in issues[:10]:
            logger.warning(f"  {issue}")
    else:
        logger.info("✓ All trade timings are valid (no data leakage detected)")
    
    return issues


def audit_statistics(trades_df: pd.DataFrame, metrics: dict):
    """Audit statistical metrics for anomalies."""
    logger.info("\n" + "=" * 80)
    logger.info("AUDIT 4: STATISTICAL ANOMALIES")
    logger.info("=" * 80)
    
    issues = []
    
    # Calculate our own metrics
    total_trades = len(trades_df)
    winners = (trades_df['r_multiple'] > 0).sum()
    losers = (trades_df['r_multiple'] < 0).sum()
    win_rate = winners / total_trades if total_trades > 0 else 0
    
    avg_winner = trades_df[trades_df['r_multiple'] > 0]['r_multiple'].mean() if winners > 0 else 0
    avg_loser = trades_df[trades_df['r_multiple'] < 0]['r_multiple'].mean() if losers > 0 else 0
    
    expectancy = (win_rate * avg_winner) + ((1 - win_rate) * avg_loser)
    
    # Verify metrics match
    if abs(metrics['win_rate'] - win_rate) > 0.01:
        issues.append({
            'type': 'WIN_RATE_MISMATCH',
            'reported': metrics['win_rate'],
            'calculated': win_rate,
        })
    
    if abs(metrics['expectancy'] - expectancy) > 0.01:
        issues.append({
            'type': 'EXPECTANCY_MISMATCH',
            'reported': metrics['expectancy'],
            'calculated': expectancy,
        })
    
    # Check for unrealistic metrics
    if metrics['sharpe_ratio'] > 3.0:
        issues.append({
            'type': 'SHARPE_TOO_HIGH',
            'value': metrics['sharpe_ratio'],
            'note': 'Sharpe > 3.0 is exceptional - verify this is not due to bugs',
        })
    
    if metrics['sortino_ratio'] > 10.0:
        issues.append({
            'type': 'SORTINO_TOO_HIGH',
            'value': metrics['sortino_ratio'],
            'note': 'Sortino > 10 is exceptionally rare - verify this is not due to bugs',
        })
    
    if metrics['profit_factor'] > 5.0:
        issues.append({
            'type': 'PROFIT_FACTOR_HIGH',
            'value': metrics['profit_factor'],
            'note': 'Profit factor > 5.0 is very high - verify salvage logic is realistic',
        })
    
    # Check avg loser
    if avg_loser > -0.3:
        issues.append({
            'type': 'AVG_LOSER_TOO_SMALL',
            'value': avg_loser,
            'note': f'Average loser is only {avg_loser:.2f}R - most trades may be salvaged before full stop',
        })
    
    if issues:
        logger.warning(f"Found {len(issues)} statistical anomalies:")
        for issue in issues:
            logger.warning(f"  {issue}")
    else:
        logger.info("✓ All statistics are within normal ranges")
    
    return issues


def audit_salvage_logic(trades_df: pd.DataFrame):
    """Audit salvage exit logic."""
    logger.info("\n" + "=" * 80)
    logger.info("AUDIT 5: SALVAGE LOGIC")
    logger.info("=" * 80)
    
    salvage_trades = trades_df[trades_df['exit_reason'] == 'SALVAGE']
    stop_trades = trades_df[trades_df['exit_reason'] == 'STOP']
    target_trades = trades_df[trades_df['exit_reason'] == 'TARGET']
    
    logger.info(f"Total trades: {len(trades_df)}")
    logger.info(f"  SALVAGE: {len(salvage_trades)} ({len(salvage_trades)/len(trades_df)*100:.1f}%)")
    logger.info(f"  STOP: {len(stop_trades)} ({len(stop_trades)/len(trades_df)*100:.1f}%)")
    logger.info(f"  TARGET: {len(target_trades)} ({len(target_trades)/len(trades_df)*100:.1f}%)")
    
    issues = []
    
    # Salvage trades stats
    if len(salvage_trades) > 0:
        logger.info(f"\nSalvage trades analysis:")
        logger.info(f"  Avg R: {salvage_trades['r_multiple'].mean():.3f}")
        logger.info(f"  Avg bars: {salvage_trades['bars_in_trade'].mean():.1f}")
        logger.info(f"  Median bars: {salvage_trades['bars_in_trade'].median():.0f}")
        
        # Check if too many salvages at exactly same bar count
        bar_counts = salvage_trades['bars_in_trade'].value_counts()
        most_common_bars = bar_counts.iloc[0] if len(bar_counts) > 0 else 0
        
        if most_common_bars > len(salvage_trades) * 0.3:
            issues.append({
                'type': 'SALVAGE_TIME_CLUSTERING',
                'note': f'{most_common_bars} salvages at {bar_counts.index[0]} bars - may indicate hardcoded time exit',
            })
    
    # Check if salvage is preventing natural stop outs
    if len(stop_trades) > 0:
        stop_avg_r = stop_trades['r_multiple'].mean()
        if stop_avg_r > -0.8:
            issues.append({
                'type': 'STOPS_NOT_FULL_LOSS',
                'avg_stop_r': stop_avg_r,
                'note': 'Average stop loss is not close to -1.0R - stops may be trailing or salvaged',
            })
    
    if issues:
        logger.warning(f"\nSalvage logic observations:")
        for issue in issues:
            logger.warning(f"  {issue}")
    else:
        logger.info("✓ Salvage logic appears reasonable")
    
    return issues


def generate_audit_report(all_issues: dict, trades_df: pd.DataFrame, metrics: dict):
    """Generate final audit report."""
    logger.info("\n" + "=" * 80)
    logger.info("FINAL AUDIT SUMMARY")
    logger.info("=" * 80)
    
    total_issues = sum(len(issues) for issues in all_issues.values())
    
    if total_issues == 0:
        logger.info("✓ ✓ ✓ BACKTEST PASSED ALL AUDITS ✓ ✓ ✓")
        logger.info("\nThe backtest results appear ACCURATE and FREE from obvious bugs.")
        logger.info("Metrics:")
        logger.info(f"  Win Rate: {metrics['win_rate']:.1%}")
        logger.info(f"  Expectancy: {metrics['expectancy']:.3f}R")
        logger.info(f"  Profit Factor: {metrics['profit_factor']:.2f}")
        logger.info(f"  Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
        logger.info(f"  Total Return: {metrics['total_return']:.1%}")
        return True
    else:
        logger.warning(f"\n⚠️  BACKTEST HAS {total_issues} ISSUES  ⚠️")
        logger.warning("\nIssues by category:")
        for category, issues in all_issues.items():
            if issues:
                logger.warning(f"  {category}: {len(issues)} issues")
        
        logger.warning("\nRecommendations:")
        if any('R_OUT_OF_RANGE' in str(issue) for issues in all_issues.values() for issue in issues):
            logger.warning("  → Review MFE/MAE tracking logic")
        if any('PROFIT_FACTOR_HIGH' in str(issue) for issues in all_issues.values() for issue in issues):
            logger.warning("  → Verify salvage logic is realistic and not overfitting")
        if any('SHARPE_TOO_HIGH' in str(issue) or 'SORTINO_TOO_HIGH' in str(issue) for issues in all_issues.values() for issue in issues):
            logger.warning("  → Results may be too good to be true - look for data leakage")
        
        return False


def main():
    """Run comprehensive backtest audit."""
    logger.info("Starting comprehensive backtest audit...")
    logger.info("=" * 80)
    
    # Load most recent run
    run_dir = "/Users/nickburner/Documents/Programming/Burner Investments/topstep/ORB(15m)/runs/multi_playbook_ES_20251009_000500"
    
    trades_df, metrics, equity_df, config = load_backtest_data(run_dir)
    
    # Run all audits
    all_issues = {}
    
    all_issues['r_multiples'] = audit_r_multiples(trades_df)
    all_issues['mfe_mae'] = audit_mfe_mae(trades_df)
    all_issues['timing'] = audit_timing(trades_df)
    all_issues['statistics'] = audit_statistics(trades_df, metrics)
    all_issues['salvage'] = audit_salvage_logic(trades_df)
    
    # Generate final report
    passed = generate_audit_report(all_issues, trades_df, metrics)
    
    if not passed:
        logger.warning("\n⚠️  Some issues found - review log for details")
    
    return passed


if __name__ == "__main__":
    passed = main()
    exit(0 if passed else 1)

