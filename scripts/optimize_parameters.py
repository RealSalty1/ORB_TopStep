"""
Parameter optimization using Optuna to find the best configuration.

Tests combinations of:
- T1 target: [1.0, 1.2, 1.3, 1.5, 1.8]R
- T2 target: [2.0, 2.5, 3.0]R  
- Breakeven trigger: [0.3, 0.4, 0.5, after_T1]
- Max stop risk: [1.4, 1.6, 1.8]R
- T1 fraction: [0.4, 0.5, 0.6]

Objective: Maximize expectancy (R per trade)
"""

import optuna
from optuna.trial import Trial
import json
import yaml
from pathlib import Path
from datetime import date
import sys
import tempfile
import shutil
from loguru import logger

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from orb_confluence.backtest.multi_instrument_orchestrator import (
    MultiInstrumentOrchestrator,
    OrchestratorConfig
)
from orb_confluence.strategy.prop_governance import TOPSTEP_50K
from orb_confluence.config.instrument_loader import reset_loader


def run_backtest_with_params(
    t1_r: float,
    t1_fraction: float,
    t2_r: float,
    breakeven_r: float,
    max_stop_r: float
) -> dict:
    """
    Run backtest with given parameters.
    
    Returns:
        dict with metrics: expectancy_r, total_r, pnl, win_rate, etc.
    """
    # Load base instrument configs and temporarily modify them
    instruments = ['ES', 'NQ', 'GC', '6E']
    config_dir = Path("orb_confluence/config/instruments")
    
    # Store original configs
    original_configs = {}
    for instrument in instruments:
        config_path = config_dir / f"{instrument}.yaml"
        with open(config_path) as f:
            original_configs[instrument] = f.read()
        
        # Load and modify
        with open(config_path) as f:
            config = yaml.safe_load(f)
        
        # Update parameters
        config['targets']['t1_r'] = float(t1_r)
        config['targets']['t1_fraction'] = float(t1_fraction)
        config['targets']['t2_r'] = float(t2_r)
        config['targets']['t2_fraction'] = float(1.0 - t1_fraction)
        config['targets']['runner_r'] = float(t2_r + 1.5)
        config['stop']['max_risk_r'] = float(max_stop_r)
        
        # Write modified config
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
    
    # Modify breakeven in enhanced_trade_manager.py temporarily
    trade_manager_path = Path("orb_confluence/strategy/enhanced_trade_manager.py")
    with open(trade_manager_path) as f:
        original_trade_manager = f.read()
    
    # Replace breakeven trigger
    modified_trade_manager = original_trade_manager.replace(
        'if not trade.moved_to_breakeven and current_r >= 0.3:',
        f'if not trade.moved_to_breakeven and current_r >= {breakeven_r}:'
    )
    with open(trade_manager_path, 'w') as f:
        f.write(modified_trade_manager)
    
    try:
        # Run backtest
        from orb_confluence.backtest.multi_instrument_orchestrator import (
            MultiInstrumentOrchestrator,
            OrchestratorConfig
        )
        
        # Create a temp output directory
        import tempfile
        temp_dir = Path(tempfile.mkdtemp())
        
        config = OrchestratorConfig(
            prop_rules=TOPSTEP_50K,
            instruments=instruments,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 10, 7),
            data_directory=Path('data_cache/databento_1m'),
            output_directory=temp_dir,
            max_concurrent_trades=2,
            correlation_aware_sizing=True
        )
        
        orchestrator = MultiInstrumentOrchestrator(config=config)
        results = orchestrator.run_backtest()
        
        # Clean up temp dir
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        # Extract metrics
        trades = results['trades']
        if len(trades) == 0:
            return {
                'expectancy_r': -999,
                'total_r': -999,
                'pnl': -999999,
                'win_rate': 0,
                'num_trades': 0
            }
        
        total_r = sum(t.outcome.realized_r for t in trades)
        total_pnl = sum(t.outcome.realized_dollars for t in trades)
        winners = [t for t in trades if t.outcome.realized_dollars > 0]
        
        metrics = {
            'expectancy_r': total_r / len(trades),
            'total_r': total_r,
            'pnl': total_pnl,
            'win_rate': len(winners) / len(trades) * 100,
            'num_trades': len(trades),
            'avg_winner_r': sum(t.outcome.realized_r for t in winners) / len(winners) if winners else 0,
            'avg_loser_r': sum(t.outcome.realized_r for t in trades if t.outcome.realized_dollars <= 0) / (len(trades) - len(winners)) if len(trades) > len(winners) else 0,
        }
        
        return metrics
        
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            'expectancy_r': -999,
            'total_r': -999,
            'pnl': -999999,
            'win_rate': 0,
            'num_trades': 0
        }
    finally:
        # Restore original configs
        for instrument in instruments:
            config_path = config_dir / f"{instrument}.yaml"
            with open(config_path, 'w') as f:
                f.write(original_configs[instrument])
        
        # Restore original trade manager
        with open(trade_manager_path, 'w') as f:
            f.write(original_trade_manager)
        
        # CRITICAL: Reset the config loader cache to force reload on next trial
        reset_loader()


def objective(trial: Trial) -> float:
    """
    Optuna objective function.
    
    Returns:
        Expectancy in R (to maximize)
    """
    # Sample parameters
    t1_r = trial.suggest_float('t1_r', 1.0, 1.8, step=0.1)
    t1_fraction = trial.suggest_float('t1_fraction', 0.4, 0.6, step=0.1)
    t2_r = trial.suggest_float('t2_r', 2.0, 3.0, step=0.5)
    breakeven_r = trial.suggest_float('breakeven_r', 0.3, 0.5, step=0.1)
    max_stop_r = trial.suggest_float('max_stop_r', 1.4, 1.8, step=0.2)
    
    # Run backtest
    metrics = run_backtest_with_params(
        t1_r=t1_r,
        t1_fraction=t1_fraction,
        t2_r=t2_r,
        breakeven_r=breakeven_r,
        max_stop_r=max_stop_r
    )
    
    # Log trial results
    logger.info(
        f"Trial {trial.number}: "
        f"T1={t1_r:.1f}R, T1_frac={t1_fraction:.1f}, "
        f"T2={t2_r:.1f}R, BE={breakeven_r:.1f}R, "
        f"Stop={max_stop_r:.1f}R | "
        f"Exp={metrics['expectancy_r']:.3f}R, "
        f"P/L=${metrics['pnl']:.0f}, "
        f"WR={metrics['win_rate']:.1f}%"
    )
    
    # Store additional metrics
    trial.set_user_attr('total_r', metrics['total_r'])
    trial.set_user_attr('pnl', metrics['pnl'])
    trial.set_user_attr('win_rate', metrics['win_rate'])
    trial.set_user_attr('num_trades', metrics['num_trades'])
    trial.set_user_attr('avg_winner_r', metrics.get('avg_winner_r', 0))
    trial.set_user_attr('avg_loser_r', metrics.get('avg_loser_r', 0))
    
    # Return expectancy to maximize
    return metrics['expectancy_r']


def main():
    """Run optimization."""
    logger.info("="*80)
    logger.info("PARAMETER OPTIMIZATION - Finding Optimal Configuration")
    logger.info("="*80)
    logger.info("Objective: Maximize Expectancy (R per trade)")
    logger.info("Dataset: 2025 YTD (1,368 trades)")
    logger.info("")
    logger.info("Parameter Ranges:")
    logger.info("  • T1 target: [1.0, 1.2, 1.3, 1.5, 1.8]R")
    logger.info("  • T1 fraction: [0.4, 0.5, 0.6]")
    logger.info("  • T2 target: [2.0, 2.5, 3.0]R")
    logger.info("  • Breakeven: [0.3, 0.4, 0.5]R")
    logger.info("  • Max stop: [1.4, 1.6, 1.8]R")
    logger.info("="*80)
    logger.info("")
    
    # Create study
    study = optuna.create_study(
        direction='maximize',
        study_name='orb_parameter_optimization',
        sampler=optuna.samplers.TPESampler(seed=42)
    )
    
    # Run optimization
    n_trials = 3  # Test 3 first to verify cache fix works
    logger.info(f"Running {n_trials} optimization trials (test run)...")
    logger.info("⏱️  Estimated time: ~10 minutes")
    logger.info("")
    
    study.optimize(objective, n_trials=n_trials, show_progress_bar=True, n_jobs=1)
    
    # Results
    logger.info("")
    logger.info("="*80)
    logger.info("OPTIMIZATION COMPLETE")
    logger.info("="*80)
    logger.info("")
    
    # Best trial
    best_trial = study.best_trial
    logger.success(f"Best Expectancy: {best_trial.value:.3f}R per trade")
    logger.info("")
    logger.info("Best Parameters:")
    logger.info(f"  • T1 target: {best_trial.params['t1_r']:.1f}R")
    logger.info(f"  • T1 fraction: {best_trial.params['t1_fraction']:.1f}")
    logger.info(f"  • T2 target: {best_trial.params['t2_r']:.1f}R")
    logger.info(f"  • Breakeven: {best_trial.params['breakeven_r']:.1f}R")
    logger.info(f"  • Max stop: {best_trial.params['max_stop_r']:.1f}R")
    logger.info("")
    logger.info("Best Performance:")
    logger.info(f"  • Expectancy: {best_trial.value:.3f}R per trade")
    logger.info(f"  • Total R: {best_trial.user_attrs['total_r']:.2f}R")
    logger.info(f"  • P/L: ${best_trial.user_attrs['pnl']:.0f}")
    logger.info(f"  • Win Rate: {best_trial.user_attrs['win_rate']:.1f}%")
    logger.info(f"  • Trades: {best_trial.user_attrs['num_trades']}")
    logger.info(f"  • Avg Winner: {best_trial.user_attrs['avg_winner_r']:.2f}R")
    logger.info(f"  • Avg Loser: {best_trial.user_attrs['avg_loser_r']:.2f}R")
    logger.info("")
    
    # Top 5 trials
    logger.info("Top 5 Configurations:")
    logger.info("-" * 80)
    top_trials = sorted(study.trials, key=lambda t: t.value, reverse=True)[:5]
    for i, trial in enumerate(top_trials, 1):
        logger.info(
            f"{i}. Exp={trial.value:.3f}R | "
            f"T1={trial.params['t1_r']:.1f}R({trial.params['t1_fraction']:.1f}), "
            f"T2={trial.params['t2_r']:.1f}R, "
            f"BE={trial.params['breakeven_r']:.1f}R, "
            f"Stop={trial.params['max_stop_r']:.1f}R | "
            f"P/L=${trial.user_attrs['pnl']:.0f}, "
            f"WR={trial.user_attrs['win_rate']:.1f}%"
        )
    
    # Save results
    output_file = Path("optimization_results.json")
    results = {
        'best_params': best_trial.params,
        'best_value': best_trial.value,
        'best_metrics': best_trial.user_attrs,
        'all_trials': [
            {
                'number': t.number,
                'params': t.params,
                'value': t.value,
                'metrics': t.user_attrs
            }
            for t in study.trials
        ]
    }
    
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    logger.info("")
    logger.info(f"Results saved to: {output_file}")
    logger.info("="*80)


if __name__ == "__main__":
    main()
