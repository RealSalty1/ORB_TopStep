"""Test advanced features on real ES data."""

from orb_confluence.features.advanced_features import AdvancedFeatures
from orb_confluence.data.databento_loader import DatabentoLoader
from loguru import logger

def main():
    """Test features on real data."""
    logger.info("Testing advanced features on real ES data")
    
    # Load data
    loader_1m = DatabentoLoader("data_cache/databento_1m")
    
    # Load recent 1m bars (full day for proper features)
    bars_1m = loader_1m.load("ES", start_date="2025-10-01", end_date="2025-10-06")
    logger.info(f"Loaded {len(bars_1m)} 1-minute bars")
    
    # Aggregate 1m to daily for baseline (last 60 days worth)
    bars_1m_copy = bars_1m.copy()
    bars_1m_copy['date'] = bars_1m_copy['timestamp_utc'].dt.date
    bars_daily_agg = bars_1m_copy.groupby('date').agg({
        'timestamp_utc': 'first',
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).reset_index(drop=True)
    logger.info(f"Aggregated to {len(bars_daily_agg)} daily bars")
    
    # Get just the most recent day for current features
    most_recent_date = bars_1m['timestamp_utc'].max().date()
    bars_1m_today = bars_1m[bars_1m['timestamp_utc'].dt.date == most_recent_date].copy()
    logger.info(f"Using {len(bars_1m_today)} bars from {most_recent_date}")
    
    # For now, use 1m data for microstructure approximation
    bars_1s = None
    logger.info("Using 1m bars for microstructure approximation (1s data processing coming soon)")
    
    # Simulate overnight bars (midnight to 9:30am)
    overnight_start = bars_1m_today[bars_1m_today['timestamp_utc'].dt.hour < 9.5]
    if len(overnight_start) > 0:
        overnight_bars = overnight_start.head(60)
        logger.info(f"Using {len(overnight_bars)} overnight bars")
    else:
        overnight_bars = None
        logger.info("No overnight bars found")
    
    # Calculate features
    features_calc = AdvancedFeatures()
    
    logger.info("\n" + "="*60)
    logger.info("CALCULATING FEATURES")
    logger.info("="*60)
    
    all_features = features_calc.calculate_all_features(
        bars_1m_today,
        bars_daily_agg,
        bars_1s,
        overnight_bars
    )
    
    # Display results
    logger.info("\n" + "="*60)
    logger.info("FEATURE RESULTS")
    logger.info("="*60)
    
    for feature_name, value in all_features.items():
        logger.info(f"{feature_name:35s}: {value:8.4f}")
    
    # Interpretation
    logger.info("\n" + "="*60)
    logger.info("REGIME INTERPRETATION")
    logger.info("="*60)
    
    vts = all_features['volatility_term_structure']
    if vts > 1.2:
        logger.info("✓ Volatility Term Structure: ELEVATED intraday vol (breakout potential)")
    elif vts < 0.8:
        logger.info("✓ Volatility Term Structure: COMPRESSED (coiling)")
    else:
        logger.info("✓ Volatility Term Structure: NORMAL")
    
    entropy = all_features['rotation_entropy']
    if entropy > 0.6:
        logger.info("✓ Rotation Entropy: HIGH (choppy, range-bound)")
    elif entropy < 0.3:
        logger.info("✓ Rotation Entropy: LOW (trending, directional)")
    else:
        logger.info("✓ Rotation Entropy: MODERATE")
    
    commitment = all_features['directional_commitment']
    if commitment > 0.7:
        logger.info("✓ Directional Commitment: STRONG (initiative behavior)")
    elif commitment < 0.3:
        logger.info("✓ Directional Commitment: WEAK (responsive, back-and-forth)")
    else:
        logger.info("✓ Directional Commitment: MODERATE")
    
    pressure = all_features['microstructure_pressure']
    if pressure > 0.2:
        logger.info("✓ Microstructure Pressure: BUYING (aggressive buyers)")
    elif pressure < -0.2:
        logger.info("✓ Microstructure Pressure: SELLING (aggressive sellers)")
    else:
        logger.info("✓ Microstructure Pressure: BALANCED")
    
    yield_curve = all_features['intraday_yield_curve']
    if yield_curve > 15:
        logger.info("✓ Intraday Yield Curve: INEFFICIENT (choppy path)")
    elif yield_curve < 8:
        logger.info("✓ Intraday Yield Curve: EFFICIENT (directional)")
    else:
        logger.info("✓ Intraday Yield Curve: MODERATE")
    
    liquidity = all_features['composite_liquidity_score']
    if liquidity > 0.7:
        logger.info("✓ Liquidity Score: HIGH (tight spreads, good depth)")
    elif liquidity < 0.3:
        logger.info("✓ Liquidity Score: LOW (wide spreads, poor depth)")
    else:
        logger.info("✓ Liquidity Score: MODERATE")
    
    logger.info("\n" + "="*60)
    logger.info("Test complete!")
    logger.info("="*60)

if __name__ == "__main__":
    main()

