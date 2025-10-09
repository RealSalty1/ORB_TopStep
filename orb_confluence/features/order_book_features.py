"""
Order Book Features

Calculates institutional-grade features from MBP-10 order book data.
These features enhance entry timing, exit timing, and risk management.

Features:
1. Order Flow Imbalance (OFI) - Buying vs selling pressure
2. Depth Imbalance - Support/resistance in full book
3. Microprice - Volume-weighted fair value
4. Volume at Best (VAB) - Liquidity concentration
5. Book Pressure - Rate of change in order flow
6. Large Order Detection - Institutional activity
7. Support/Resistance Clusters - Dynamic stops
8. Book Exhaustion - Correlation filter

Author: Nick Burner
Date: October 9, 2025
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, List, Tuple
from loguru import logger


class OrderBookFeatures:
    """
    Calculate advanced features from MBP-10 order book data.
    
    Usage:
        features = OrderBookFeatures()
        
        # Single snapshot features
        ofi = features.order_flow_imbalance(snapshot)
        depth = features.depth_imbalance(snapshot)
        microprice = features.microprice(snapshot)
        
        # Time series features
        pressure = features.book_pressure(df_history)
        exhaustion = features.detect_exhaustion(df_recent, direction='SHORT')
    """
    
    def __init__(self):
        """Initialize OrderBookFeatures calculator."""
        logger.debug("OrderBookFeatures initialized")
    
    # ========================================================================
    # CORE FEATURES (SINGLE SNAPSHOT)
    # ========================================================================
    
    def order_flow_imbalance(
        self,
        snapshot: Dict,
        level: int = 0
    ) -> float:
        """
        Calculate Order Flow Imbalance (OFI) at specific level.
        
        OFI = (Bid Size - Ask Size) / (Bid Size + Ask Size)
        
        Range: -1 (all selling) to +1 (all buying)
        
        Args:
            snapshot: Order book snapshot dictionary
            level: Book level (0 = best, 9 = 10th level)
            
        Returns:
            OFI value between -1 and 1
            
        Interpretation:
            > 0.3: Strong buying pressure (good for LONG entries)
            < -0.3: Strong selling pressure (good for SHORT entries)
            Near 0: Balanced (neutral or choppy)
        """
        bid_col = f'bid_sz_{level:02d}'
        ask_col = f'ask_sz_{level:02d}'
        
        bid_size = snapshot.get(bid_col, 0)
        ask_size = snapshot.get(ask_col, 0)
        
        if bid_size + ask_size == 0:
            return 0.0
        
        ofi = (bid_size - ask_size) / (bid_size + ask_size)
        
        return float(ofi)
    
    def depth_imbalance(
        self,
        snapshot: Dict,
        levels: int = 10
    ) -> float:
        """
        Calculate Depth Imbalance across all levels.
        
        Sum all bid/ask sizes across N levels and compare.
        
        Args:
            snapshot: Order book snapshot dictionary
            levels: Number of levels to sum (1-10)
            
        Returns:
            Depth imbalance between -1 and 1
            
        Interpretation:
            > 0.3: Strong bid support (confirms LONG)
            < -0.3: Strong ask pressure (confirms SHORT)
        """
        total_bid = 0
        total_ask = 0
        
        for level in range(levels):
            bid_col = f'bid_sz_{level:02d}'
            ask_col = f'ask_sz_{level:02d}'
            
            total_bid += snapshot.get(bid_col, 0)
            total_ask += snapshot.get(ask_col, 0)
        
        if total_bid + total_ask == 0:
            return 0.0
        
        depth_imb = (total_bid - total_ask) / (total_bid + total_ask)
        
        return float(depth_imb)
    
    def microprice(
        self,
        snapshot: Dict
    ) -> float:
        """
        Calculate microprice (volume-weighted mid).
        
        Microprice = (Bid * Ask Size + Ask * Bid Size) / (Bid Size + Ask Size)
        
        This is the "true" fair value accounting for order book pressure.
        
        Args:
            snapshot: Order book snapshot dictionary
            
        Returns:
            Microprice (fair value)
            
        Use Case:
            - Trail stops at microprice instead of VWAP
            - More responsive to real-time supply/demand
        """
        bid_px = snapshot.get('bid_px_00', 0)
        ask_px = snapshot.get('ask_px_00', 0)
        bid_sz = snapshot.get('bid_sz_00', 0)
        ask_sz = snapshot.get('ask_sz_00', 0)
        
        if bid_sz + ask_sz == 0:
            # Fall back to mid
            return (bid_px + ask_px) / 2 if (bid_px + ask_px) > 0 else 0.0
        
        microprice = (bid_px * ask_sz + ask_px * bid_sz) / (bid_sz + ask_sz)
        
        return float(microprice)
    
    def volume_at_best(
        self,
        snapshot: Dict
    ) -> int:
        """
        Calculate total volume at best bid/ask.
        
        VAB = Bid Size + Ask Size (at level 0)
        
        Args:
            snapshot: Order book snapshot dictionary
            
        Returns:
            Total contracts at best
            
        Interpretation:
            > 200: Thick book (more size acceptable)
            < 50: Thin book (reduce size, widerwid stops)
        """
        bid_sz = snapshot.get('bid_sz_00', 0)
        ask_sz = snapshot.get('ask_sz_00', 0)
        
        return int(bid_sz + ask_sz)
    
    def liquidity_ratio(
        self,
        snapshot: Dict,
        levels: int = 10
    ) -> float:
        """
        Calculate liquidity concentration ratio.
        
        Ratio = (Volume at Best) / (Total Volume in 10 levels)
        
        Args:
            snapshot: Order book snapshot dictionary
            levels: Number of levels to consider
            
        Returns:
            Ratio between 0 and 1
            
        Interpretation:
            > 0.3: Concentrated at best (easier to move)
            < 0.1: Spread across levels (harder to move)
        """
        vab = self.volume_at_best(snapshot)
        
        total_volume = 0
        for level in range(levels):
            total_volume += snapshot.get(f'bid_sz_{level:02d}', 0)
            total_volume += snapshot.get(f'ask_sz_{level:02d}', 0)
        
        if total_volume == 0:
            return 0.0
        
        ratio = vab / total_volume
        
        return float(ratio)
    
    def spread(
        self,
        snapshot: Dict
    ) -> float:
        """
        Calculate bid-ask spread in points.
        
        Args:
            snapshot: Order book snapshot dictionary
            
        Returns:
            Spread in points
        """
        bid_px = snapshot.get('bid_px_00', 0)
        ask_px = snapshot.get('ask_px_00', 0)
        
        return float(ask_px - bid_px)
    
    # ========================================================================
    # TIME SERIES FEATURES (MULTIPLE SNAPSHOTS)
    # ========================================================================
    
    def book_pressure(
        self,
        df: pd.DataFrame,
        window: int = 10
    ) -> pd.Series:
        """
        Calculate book pressure (rate of change in order flow).
        
        Pressure = Change in (Bid Size - Ask Size) over time
        
        Args:
            df: DataFrame with bid_sz_00 and ask_sz_00 columns
            window: Lookback window for diff
            
        Returns:
            Series of pressure values
            
        Interpretation:
            Positive spike: Aggressive buying
            Negative spike: Aggressive selling
        """
        if 'bid_sz_00' not in df.columns or 'ask_sz_00' not in df.columns:
            logger.warning("Missing bid/ask size columns")
            return pd.Series()
        
        net_volume = df['bid_sz_00'] - df['ask_sz_00']
        pressure = net_volume.diff(window)
        
        return pressure
    
    def detect_large_orders(
        self,
        snapshot: Dict,
        threshold: int = 100,
        levels: int = 10
    ) -> Dict[str, List[Tuple[float, int]]]:
        """
        Detect large orders in the book (institutional activity).
        
        Args:
            snapshot: Order book snapshot dictionary
            threshold: Minimum size to consider "large"
            levels: Number of levels to scan
            
        Returns:
            Dictionary with 'bids' and 'asks' lists of (price, size) tuples
            
        Use Case:
            - Exit before hitting large opposing orders
            - Place stops beyond large supporting orders
        """
        large_bids = []
        large_asks = []
        
        for level in range(levels):
            bid_px = snapshot.get(f'bid_px_{level:02d}')
            ask_px = snapshot.get(f'ask_px_{level:02d}')
            bid_sz = snapshot.get(f'bid_sz_{level:02d}', 0)
            ask_sz = snapshot.get(f'ask_sz_{level:02d}', 0)
            
            if bid_sz >= threshold and bid_px is not None:
                large_bids.append((float(bid_px), int(bid_sz)))
            
            if ask_sz >= threshold and ask_px is not None:
                large_asks.append((float(ask_px), int(ask_sz)))
        
        return {
            'bids': large_bids,
            'asks': large_asks
        }
    
    def find_support_resistance(
        self,
        snapshot: Dict,
        direction: str,
        levels: int = 10
    ) -> Tuple[Optional[float], int]:
        """
        Find strongest support/resistance level in book.
        
        Args:
            snapshot: Order book snapshot dictionary
            direction: 'LONG' or 'SHORT'
            levels: Number of levels to scan
            
        Returns:
            Tuple of (price, size) for strongest cluster
            
        Use Case:
            - Place stops 2-3 ticks beyond strongest support (LONG)
            - Place stops 2-3 ticks beyond strongest resistance (SHORT)
        """
        max_size = 0
        best_price = None
        
        if direction == 'LONG':
            # Find strongest bid (support)
            for level in range(levels):
                bid_sz = snapshot.get(f'bid_sz_{level:02d}', 0)
                if bid_sz > max_size:
                    max_size = bid_sz
                    best_price = snapshot.get(f'bid_px_{level:02d}')
        
        else:  # SHORT
            # Find strongest ask (resistance)
            for level in range(levels):
                ask_sz = snapshot.get(f'ask_sz_{level:02d}', 0)
                if ask_sz > max_size:
                    max_size = ask_sz
                    best_price = snapshot.get(f'ask_px_{level:02d}')
        
        return (float(best_price) if best_price is not None else None, int(max_size))
    
    def detect_exhaustion(
        self,
        df_recent: pd.DataFrame,
        direction: str,
        ofi_threshold: float = 0.3,
        depth_threshold: float = 0.2,
        window: int = 10
    ) -> Tuple[bool, str]:
        """
        Detect book exhaustion (for correlation filter).
        
        Exhaustion signals:
        1. OFI weakening (moving toward 0)
        2. Depth imbalance decreasing
        3. Book pressure slowing
        
        Args:
            df_recent: Recent order book snapshots
            direction: Current position direction ('LONG' or 'SHORT')
            ofi_threshold: OFI threshold for "strong"
            depth_threshold: Depth threshold for "supported"
            window: Lookback window
            
        Returns:
            Tuple of (is_exhausted, reason)
            
        Use Case:
            Sept 14-15 fix - don't enter if already in position
            AND book shows exhaustion
        """
        if len(df_recent) < window:
            return False, "INSUFFICIENT_DATA"
        
        # Calculate OFI series
        ofi_values = []
        for idx in range(len(df_recent)):
            snapshot = df_recent.iloc[idx].to_dict()
            ofi = self.order_flow_imbalance(snapshot)
            ofi_values.append(ofi)
        
        ofi_series = pd.Series(ofi_values)
        
        # Get recent trend
        recent_ofi = ofi_series.iloc[-window:]
        ofi_mean = recent_ofi.mean()
        ofi_std = recent_ofi.std()
        current_ofi = ofi_series.iloc[-1]
        
        # Check for weakening
        if direction == 'SHORT':
            # Was strong sell (OFI < -0.3)
            if ofi_mean < -ofi_threshold:
                # Now weaker (moving toward 0)
                if current_ofi > ofi_mean + ofi_std:
                    return True, 'WEAKENING_SELL_FLOW'
        
        elif direction == 'LONG':
            # Was strong buy (OFI > 0.3)
            if ofi_mean > ofi_threshold:
                # Now weaker
                if current_ofi < ofi_mean - ofi_std:
                    return True, 'WEAKENING_BUY_FLOW'
        
        # Check depth imbalance
        current_snapshot = df_recent.iloc[-1].to_dict()
        depth_imb = self.depth_imbalance(current_snapshot)
        
        if abs(depth_imb) < 0.1:  # Balanced book = exhaustion
            return True, 'BALANCED_BOOK'
        
        return False, 'STILL_STRONG'
    
    # ========================================================================
    # BATCH CALCULATIONS
    # ========================================================================
    
    def calculate_all_features(
        self,
        snapshot: Dict,
        levels: int = 10
    ) -> Dict[str, float]:
        """
        Calculate all features for a single snapshot.
        
        Args:
            snapshot: Order book snapshot dictionary
            levels: Number of levels to use
            
        Returns:
            Dictionary with all feature values
        """
        features = {
            'ofi': self.order_flow_imbalance(snapshot),
            'depth_imbalance': self.depth_imbalance(snapshot, levels),
            'microprice': self.microprice(snapshot),
            'volume_at_best': self.volume_at_best(snapshot),
            'liquidity_ratio': self.liquidity_ratio(snapshot, levels),
            'spread': self.spread(snapshot),
        }
        
        # Add large order detection
        large_orders = self.detect_large_orders(snapshot, threshold=100, levels=levels)
        features['large_bid_count'] = len(large_orders['bids'])
        features['large_ask_count'] = len(large_orders['asks'])
        
        return features


if __name__ == "__main__":
    # Demo usage
    from orb_confluence.data.mbp10_loader import MBP10Loader
    
    loader = MBP10Loader(data_directory="data_cache/GLBX-20251008-HHT7VXJSSJ")
    features_calc = OrderBookFeatures()
    
    # Get snapshot
    snapshot = loader.get_snapshot_at("2025-09-15", "09:30:00")
    
    if snapshot:
        # Calculate all features
        features = features_calc.calculate_all_features(snapshot)
        
        print("Order Book Features:")
        print("=" * 50)
        for name, value in features.items():
            print(f"  {name:25s}: {value:.4f}" if isinstance(value, float) else f"  {name:25s}: {value}")
        
        # Check for large orders
        large_orders = features_calc.detect_large_orders(snapshot, threshold=50)
        print(f"\nLarge Bids: {len(large_orders['bids'])}")
        print(f"Large Asks: {len(large_orders['asks'])}")
        
        # Support/resistance
        support, support_size = features_calc.find_support_resistance(snapshot, 'LONG')
        resistance, resistance_size = features_calc.find_support_resistance(snapshot, 'SHORT')
        print(f"\nStrongest Support: ${support:.2f} x {support_size}")
        print(f"Strongest Resistance: ${resistance:.2f} x {resistance_size}")

