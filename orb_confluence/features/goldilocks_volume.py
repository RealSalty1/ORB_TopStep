"""Goldilocks volume filter: not too high, not too low, just right.

This module implements the volume quality filter described in section 5 of the strategy doc.
"""

import numpy as np
import pandas as pd
from typing import Tuple, Dict, Any
from loguru import logger


class TimeOfDayVolumeProfile:
    """Build and maintain time-of-day volume expectations."""
    
    def __init__(self, lookback_sessions: int = 30):
        """Initialize with lookback period."""
        self.lookback_sessions = lookback_sessions
        self.minute_profiles: Dict[int, list] = {}  # minute_index -> [volumes]
        self.session_count = 0
    
    def update(self, session_bars: pd.DataFrame):
        """Update profile with a new session's data.
        
        Args:
            session_bars: DataFrame with 'timestamp' and 'volume'
        """
        if len(session_bars) == 0:
            return
        
        # Extract minute of day
        session_bars = session_bars.copy()
        session_bars['minute_of_day'] = (
            session_bars['timestamp'].dt.hour * 60 + 
            session_bars['timestamp'].dt.minute
        )
        
        # Update profiles
        for idx, row in session_bars.iterrows():
            minute = int(row['minute_of_day'])
            volume = float(row['volume'])
            
            if minute not in self.minute_profiles:
                self.minute_profiles[minute] = []
            
            self.minute_profiles[minute].append(volume)
            
            # Keep only last N sessions
            if len(self.minute_profiles[minute]) > self.lookback_sessions:
                self.minute_profiles[minute].pop(0)
        
        self.session_count += 1
    
    def get_expected_volume(self, minute_of_day: int) -> float:
        """Get expected volume for a minute of day."""
        if minute_of_day not in self.minute_profiles:
            return 0.0
        
        volumes = self.minute_profiles[minute_of_day]
        if len(volumes) == 0:
            return 0.0
        
        return float(np.median(volumes))
    
    def get_volume_stats(self, minute_of_day: int) -> Dict[str, float]:
        """Get statistical measures for a minute."""
        if minute_of_day not in self.minute_profiles:
            return {'median': 0.0, 'mean': 0.0, 'std': 0.0, 'p95': 0.0}
        
        volumes = np.array(self.minute_profiles[minute_of_day])
        if len(volumes) == 0:
            return {'median': 0.0, 'mean': 0.0, 'std': 0.0, 'p95': 0.0}
        
        return {
            'median': float(np.median(volumes)),
            'mean': float(np.mean(volumes)),
            'std': float(np.std(volumes)),
            'p95': float(np.percentile(volumes, 95))
        }


class GoldilocksVolumeFilter:
    """Multi-layer volume quality filter.
    
    Filters out:
    - Too low volume (no participation)
    - Too high volume (news spike / trap risk)
    - Spiky volume (single bar shocks)
    - Lethargic opens (low directional energy)
    """
    
    def __init__(
        self,
        cum_ratio_min: float = 0.85,
        cum_ratio_max: float = 1.35,
        spike_threshold_mult: float = 2.2,
        min_drive_energy: float = 0.35,
        lookback_sessions: int = 30
    ):
        """Initialize filter."""
        self.cum_ratio_min = cum_ratio_min
        self.cum_ratio_max = cum_ratio_max
        self.spike_threshold_mult = spike_threshold_mult
        self.min_drive_energy = min_drive_energy
        
        self.tod_profile = TimeOfDayVolumeProfile(lookback_sessions)
        
        # Historical ratios for z-score
        self.historical_ratios = []
        self.max_history = 100
    
    def update_profile(self, session_bars: pd.DataFrame):
        """Update time-of-day profile with session data."""
        self.tod_profile.update(session_bars)
    
    def analyze_or_volume(
        self,
        or_bars: pd.DataFrame,
        or_width: float
    ) -> Dict[str, Any]:
        """Analyze opening range volume quality.
        
        Args:
            or_bars: DataFrame with OR window bars (timestamp, volume, open, close)
            or_width: Opening range width (high - low)
        
        Returns:
            Dictionary with volume metrics and pass/fail
        """
        if len(or_bars) == 0:
            return self._empty_result()
        
        # Calculate minute of day for each bar
        or_bars = or_bars.copy()
        or_bars['minute_of_day'] = (
            or_bars['timestamp'].dt.hour * 60 + 
            or_bars['timestamp'].dt.minute
        )
        
        # 1. Cumulative volume vs expected
        cum_volume = or_bars['volume'].sum()
        expected_volumes = [
            self.tod_profile.get_expected_volume(int(minute))
            for minute in or_bars['minute_of_day']
        ]
        expected_cum = sum(expected_volumes)
        
        if expected_cum == 0:
            logger.warning("No expected volume data - profile not yet built")
            return self._empty_result()
        
        cum_vol_ratio = cum_volume / expected_cum
        
        # 2. Z-score (if we have history)
        self.historical_ratios.append(cum_vol_ratio)
        if len(self.historical_ratios) > self.max_history:
            self.historical_ratios.pop(0)
        
        if len(self.historical_ratios) > 5:
            vol_z = (cum_vol_ratio - np.mean(self.historical_ratios)) / (
                np.std(self.historical_ratios) + 1e-8
            )
        else:
            vol_z = 0.0
        
        # 3. Spike detection
        spike_detected = False
        max_spike_ratio = 0.0
        
        for idx, row in or_bars.iterrows():
            minute = int(row['minute_of_day'])
            stats = self.tod_profile.get_volume_stats(minute)
            median_vol = stats['median']
            
            if median_vol > 0:
                spike_ratio = row['volume'] / median_vol
                max_spike_ratio = max(max_spike_ratio, spike_ratio)
                
                if spike_ratio > self.spike_threshold_mult:
                    spike_detected = True
        
        # 4. Opening drive energy
        # Measures directional momentum vs range width
        if or_width > 0:
            drive_energy = or_bars['close'].sub(or_bars['open']).abs().sum() / or_width
        else:
            drive_energy = 0.0
        
        # 5. Volume quality score (0-1 composite)
        # Component 1: Band proximity (how close to 1.0)
        band_score = max(0.0, 1.0 - abs(cum_vol_ratio - 1.0) / 0.5)
        
        # Component 2: No spike (boolean)
        spike_score = 0.0 if spike_detected else 1.0
        
        # Component 3: Drive energy normalized
        energy_score = min(1.0, drive_energy / 1.0)  # Normalize to 1.0 as "full"
        
        # Weighted composite
        volume_quality_score = (
            0.5 * band_score +
            0.3 * spike_score +
            0.2 * energy_score
        )
        
        # 6. Pass/fail determination
        passes_goldilocks = (
            self.cum_ratio_min <= cum_vol_ratio <= self.cum_ratio_max and
            not spike_detected and
            drive_energy >= self.min_drive_energy
        )
        
        return {
            'cum_volume_or': float(cum_volume),
            'expected_volume_or': float(expected_cum),
            'cum_vol_ratio': float(cum_vol_ratio),
            'vol_z_score': float(vol_z),
            'spike_detected': spike_detected,
            'max_spike_ratio': float(max_spike_ratio),
            'opening_drive_energy': float(drive_energy),
            'volume_quality_score': float(volume_quality_score),
            'passes_goldilocks': passes_goldilocks,
            'fail_reasons': self._get_fail_reasons(
                cum_vol_ratio, spike_detected, drive_energy
            )
        }
    
    def _get_fail_reasons(
        self,
        cum_vol_ratio: float,
        spike_detected: bool,
        drive_energy: float
    ) -> list:
        """Get list of failure reasons if applicable."""
        reasons = []
        
        if cum_vol_ratio < self.cum_ratio_min:
            reasons.append(f"volume_too_low ({cum_vol_ratio:.2f} < {self.cum_ratio_min})")
        
        if cum_vol_ratio > self.cum_ratio_max:
            reasons.append(f"volume_too_high ({cum_vol_ratio:.2f} > {self.cum_ratio_max})")
        
        if spike_detected:
            reasons.append("volume_spike_detected")
        
        if drive_energy < self.min_drive_energy:
            reasons.append(f"drive_energy_low ({drive_energy:.2f} < {self.min_drive_energy})")
        
        return reasons
    
    def _empty_result(self) -> Dict[str, Any]:
        """Return empty/default result."""
        return {
            'cum_volume_or': 0.0,
            'expected_volume_or': 0.0,
            'cum_vol_ratio': 0.0,
            'vol_z_score': 0.0,
            'spike_detected': False,
            'max_spike_ratio': 0.0,
            'opening_drive_energy': 0.0,
            'volume_quality_score': 0.0,
            'passes_goldilocks': False,
            'fail_reasons': ['insufficient_data']
        }


def create_goldilocks_filter_from_config(instrument_config) -> GoldilocksVolumeFilter:
    """Create Goldilocks filter from instrument configuration."""
    return GoldilocksVolumeFilter(
        cum_ratio_min=instrument_config.volume_cum_ratio_min,
        cum_ratio_max=instrument_config.volume_cum_ratio_max,
        spike_threshold_mult=instrument_config.volume_spike_threshold_mult,
        min_drive_energy=instrument_config.volume_min_drive_energy,
        lookback_sessions=30
    )
