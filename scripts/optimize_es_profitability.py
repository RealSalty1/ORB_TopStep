"""
ES Profitability Optimization - Round 2

Focus: Let winners run to 1.5R+ to fix R:R mismatch
Current: Avg Winner = 0.53R, Avg Loser = -1.27R (0.417:1)
Goal: Avg Winner = 1.0R+, push expectancy to +0.05R to +0.15R
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

sys.path.insert(0, str(Path(__file__).parent.parent))

from orb_confluence.backtest.multi_instrument_orchestrator import (
    MultiInstrumentOrchestrator,
    OrchestratorConfig
)
from orb_confluence.strategy.prop_governance import TOPSTEP_50K
from orb_confluence.config.instrument_loader import reset_loader


def run_es_backtest(
    t1_r: float,
    t1_fraction: float,
    t2_r: float,
    breakeven_r: float,
    max_stop_r: float
) -> dict:
    """Run ES backtest with profitability-focused parameters."""
    
    config_path = Path("orb_confluence/config/instruments/ES.yaml")
    
    # Store original
    with open(config_path) as f:
        original_config = f.read()
    
    # Modify
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    config['targets']['t1_r'] = float(t1_r)
    config['targets']['t1_fraction'] = float(t1_fraction)
    config['targets']['t2_r'] = float(t2_r)
    config['targets']['t2_fraction'] = float(1.0 - t1_fraction)
    config['targets']['runner_r'] = float(t2_r + 1.5)
    config['stop']['max_risk_r'] = float(max_stop_r)
    
    with open(config_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)
    
    # Modify breakeven
    trade_manager_path = Path("orb_confluence/strategy/enhanced_trade_manager.py")
    with open(trade_manager_path) as f:
        original_trade_manager = f.read()
    
    modified_trade_manager = original_trade_manager.replace(
        'if not trade.moved_to_breakeven and current_r >= 0.4:',
        f'if not trade.moved_to_breakeven and current_r >= {breakeven_r}:'
    )
    with open(trade_manager_path, 'w') as f:
        f.write(modified_trade_manager)
    
    try:
        temp_dir = Path(tempfile.mkdtemp())
        
        orchestrator_config = OrchestratorConfig(
            prop_rules=TOPSTEP_50K,
            instruments=['ES'],
            start_date=date(2025, 1, 1),
            end_date=date(2025, 10, 7),
            data_directory=Path('data_cache/databento_1m'),
            output_directory=temp_dir,
            max_concurrent_trades=2,
            correlation_aware_sizing=False
        )
        
        orchestrator = MultiInstrumentOrchestrator(config=orchestrator_config)
        results = orchestrator.run_backtest()
        
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        trades = results['trades']
        if len(trades) == 0:
            return {'expectancy_r': -999, 'total_r': -999, 'pnl': -999999, 
                    'win_rate': 0, 'num_trades': 0, 'avg_winner_r': 0, 
                    'avg_loser_r': 0, 'rr_ratio': 0}
        
        total_r = sum(t.outcome.realized_r for t in trades)
        total_pnl = sum(t.outcome.realized_dollars for t in trades)
        winners = [t for t in trades if t.outcome.realized_dollars > 0]
        losers = [t for t in trades if t.outcome.realized_dollars <= 0]
        
        avg_winner_r = sum(t.outcome.realized_r for t in winners) / len(winners) if winners else 0
        avg_loser_r = sum(t.outcome.realized_r for t in losers) / len(losers) if losers else -1
        rr_ratio = abs(avg_winner_r / avg_loser_r) if avg_loser_r != 0 else 0
        
        return {
            'expectancy_r': total_r / len(trades),
            'total_r': total_r,
            'pnl': total_pnl,
            'win_rate': len(winners) / len(trades) * 100,
            'num_trades': len(trades),
            'avg_winner_r': avg_winner_r,
            'avg_loser_r': avg_loser_r,
            'rr_ratio': rr_ratio
        }
        
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {'expectancy_r': -999, 'total_r': -999, 'pnl': -999999,
                'win_rate': 0, 'num_trades': 0, 'avg_winner_r': 0,
                'avg_loser_r': 0, 'rr_ratio': 0}
    finally:
        with open(config_path, 'w') as f:
            f.write(original_config)
        with open(trade_manager_path, 'w') as f:
            f.write(original_trade_manager)
        reset_loader()


def objective(trial: Trial) -> float:
    """Optimize for profitability by letting winners run."""
    
    # AGGRESSIVE: Test much higher T1 targets
    t1_r = trial.suggest_float('t1_r', 1.2, 2.5, step=0.3)  # 1.2, 1.5, 1.8, 2.1, 2.4
    
    # Take LESS off at T1 to leave more for runners
    t1_fraction = trial.suggest_float('t1_fraction', 0.3, 0.5, step=0.1)  # 30%, 40%, 50%
    
    # Higher T2
    t2_r = trial.suggest_float('t2_r', 3.0, 4.0, step=0.5)  # 3.0, 3.5, 4.0
    
    # Later breakeven to avoid choking
    breakeven_r = trial.suggest_float('breakeven_r', 0.5, 0.8, step=0.1)  # 0.5, 0.6, 0.7, 0.8
    
    # Keep stop tight
    max_stop_r = trial.suggest_float('max_stop_r', 1.2, 1.6, step=0.2)  # 1.2, 1.4, 1.6
    
    metrics = run_es_backtest(
        t1_r=t1_r,
        t1_fraction=t1_fraction,
        t2_r=t2_r,
        breakeven_r=breakeven_r,
        max_stop_r=max_stop_r
    )
    
    logger.info(
        f"Trial {trial.number}: "
        f"T1={t1_r:.1f}R({t1_fraction:.1f}), T2={t2_r:.1f}R, "
        f"BE={breakeven_r:.1f}R, Stop={max_stop_r:.1f}R | "
        f"Exp={metrics['expectancy_r']:.3f}R, "
        f"AvgWin={metrics['avg_winner_r']:.2f}R, "
        f"R:R={metrics['rr_ratio']:.3f}:1, "
        f"WR={metrics['win_rate']:.1f}%, "
        f"P/L=${metrics['pnl']:.0f}"
    )
    
    trial.set_user_attr('total_r', metrics['total_r'])
    trial.set_user_attr('pnl', metrics['pnl'])
    trial.set_user_attr('win_rate', metrics['win_rate'])
    trial.set_user_attr('num_trades', metrics['num_trades'])
    trial.set_user_attr('avg_winner_r', metrics['avg_winner_r'])
    trial.set_user_attr('avg_loser_r', metrics['avg_loser_r'])
    trial.set_user_attr('rr_ratio', metrics['rr_ratio'])
    
    return metrics['expectancy_r']


def main():
    logger.info("="*80)
    logger.info("ES PROFITABILITY OPTIMIZATION - Round 2")
    logger.info("="*80)
    logger.info("Goal: Push expectancy from -0.219R → POSITIVE")
    logger.info("Strategy: Let winners run to 1.5R-2.5R")
    logger.info("")
    logger.info("Parameter Ranges (AGGRESSIVE):")
    logger.info("  • T1 target: [1.2, 1.5, 1.8, 2.1, 2.4]R (vs 1.0R now)")
    logger.info("  • T1 fraction: [0.3, 0.4, 0.5] (vs 0.6 now)")
    logger.info("  • T2 target: [3.0, 3.5, 4.0]R")
    logger.info("  • Breakeven: [0.5, 0.6, 0.7, 0.8]R (LATER)")
    logger.info("  • Max stop: [1.2, 1.4, 1.6]R")
    logger.info("="*80)
    logger.info("")
    
    study = optuna.create_study(
        direction='maximize',
        study_name='es_profitability',
        sampler=optuna.samplers.TPESampler(seed=42)
    )
    
    n_trials = 25  # More trials to explore the space
    logger.info(f"Running {n_trials} optimization trials...")
    logger.info("⏱️  Estimated time: ~40-60 minutes")
    logger.info("")
    
    study.optimize(objective, n_trials=n_trials, show_progress_bar=True, n_jobs=1)
    
    logger.info("")
    logger.info("="*80)
    logger.info("PROFITABILITY OPTIMIZATION COMPLETE")
    logger.info("="*80)
    logger.info("")
    
    best_trial = study.best_trial
    logger.success(f"🎯 Best Expectancy: {best_trial.value:.3f}R per trade")
    
    if best_trial.value > 0:
        logger.success(f"🎉 PROFITABLE! +${best_trial.user_attrs['pnl']:.0f}")
    elif best_trial.value > -0.1:
        logger.info(f"💪 Near breakeven! ${best_trial.user_attrs['pnl']:.0f}")
    else:
        logger.warning(f"⚠️  Still losing ${best_trial.user_attrs['pnl']:.0f}")
    
    logger.info("")
    logger.info("Best Parameters:")
    logger.info(f"  • T1 target: {best_trial.params['t1_r']:.1f}R")
    logger.info(f"  • T1 fraction: {best_trial.params['t1_fraction']:.1f}")
    logger.info(f"  • T2 target: {best_trial.params['t2_r']:.1f}R")
    logger.info(f"  • Breakeven: {best_trial.params['breakeven_r']:.1f}R")
    logger.info(f"  • Max stop: {best_trial.params['max_stop_r']:.1f}R")
    logger.info("")
    logger.info("Best Performance:")
    logger.info(f"  • Expectancy: {best_trial.value:.3f}R")
    logger.info(f"  • P/L: ${best_trial.user_attrs['pnl']:.0f}")
    logger.info(f"  • Win Rate: {best_trial.user_attrs['win_rate']:.1f}%")
    logger.info(f"  • Avg Winner: {best_trial.user_attrs['avg_winner_r']:.2f}R")
    logger.info(f"  • Avg Loser: {best_trial.user_attrs['avg_loser_r']:.2f}R")
    logger.info(f"  • R:R Ratio: {best_trial.user_attrs['rr_ratio']:.3f}:1")
    logger.info("")
    
    # Top 5
    logger.info("Top 5 Configurations:")
    logger.info("-" * 80)
    top_trials = sorted(study.trials, key=lambda t: t.value, reverse=True)[:5]
    for i, trial in enumerate(top_trials, 1):
        status = "✅" if trial.value > 0 else "⚠️" if trial.value > -0.1 else "❌"
        logger.info(
            f"{i}. {status} Exp={trial.value:.3f}R | "
            f"T1={trial.params['t1_r']:.1f}R({trial.params['t1_fraction']:.1f}), "
            f"BE={trial.params['breakeven_r']:.1f}R | "
            f"AvgWin={trial.user_attrs['avg_winner_r']:.2f}R, "
            f"R:R={trial.user_attrs['rr_ratio']:.3f}:1, "
            f"P/L=${trial.user_attrs['pnl']:.0f}"
        )
    
    # Save
    output_file = Path("optimization_es_profitability.json")
    results = {
        'instrument': 'ES',
        'optimization': 'profitability_round2',
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
