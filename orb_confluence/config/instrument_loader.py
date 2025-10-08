"""Load and manage per-instrument configuration."""

from pathlib import Path
from typing import Dict, Any
import yaml
from loguru import logger


class InstrumentConfig:
    """Instrument-specific configuration."""
    
    def __init__(self, config_dict: Dict[str, Any]):
        """Initialize from config dictionary."""
        self.raw = config_dict
        self.symbol = config_dict['symbol']
        self.display_name = config_dict['display_name']
        self.yahoo_symbol = config_dict['yahoo_symbol']
        
        # Contract specs
        self.tick_size = config_dict['tick_size']
        self.tick_value = config_dict['tick_value']
        self.tick_value_micro = config_dict['tick_value_micro']
        
        # Session
        self.session_start = config_dict['session_start']
        self.session_end = config_dict['session_end']
        
        # OR parameters
        self.or_base_minutes = config_dict['or']['base_minutes']
        self.or_min_minutes = config_dict['or']['min_minutes']
        self.or_max_minutes = config_dict['or']['max_minutes']
        self.or_low_vol_threshold = config_dict['or']['low_vol_threshold']
        self.or_high_vol_threshold = config_dict['or']['high_vol_threshold']
        
        # Validity
        self.validity_min_width_norm = config_dict['validity']['min_width_norm']
        self.validity_max_width_norm = config_dict['validity']['max_width_norm']
        self.validity_min_width_points = config_dict['validity']['min_width_points']
        self.validity_max_width_points = config_dict['validity']['max_width_points']
        
        # Buffer
        self.buffer_base_points = config_dict['buffer']['base_points']
        self.buffer_volatility_scalar = config_dict['buffer']['volatility_scalar']
        self.buffer_min = config_dict['buffer']['min_buffer']
        self.buffer_max = config_dict['buffer']['max_buffer']
        
        # Stop
        self.stop_min_points = config_dict['stop']['min_points']
        self.stop_max_risk_r = config_dict['stop']['max_risk_r']
        self.stop_atr_cap_mult = config_dict['stop']['atr_cap_mult']
        
        # Targets
        self.target_t1_r = config_dict['targets']['t1_r']
        self.target_t1_fraction = config_dict['targets']['t1_fraction']
        self.target_t2_r = config_dict['targets']['t2_r']
        self.target_t2_fraction = config_dict['targets']['t2_fraction']
        self.target_runner_r = config_dict['targets']['runner_r']
        self.target_runner_trail_mode = config_dict['targets']['runner_trail_mode']
        
        # Time stop
        self.time_stop_enabled = config_dict['time_stop']['enabled']
        self.time_stop_minutes = config_dict['time_stop']['minutes']
        self.time_stop_min_progress_r = config_dict['time_stop']['min_progress_r']
        
        # Volume
        self.volume_cum_ratio_min = config_dict['volume']['cum_ratio_min']
        self.volume_cum_ratio_max = config_dict['volume']['cum_ratio_max']
        self.volume_spike_threshold_mult = config_dict['volume']['spike_threshold_mult']
        self.volume_min_drive_energy = config_dict['volume']['min_drive_energy']
        
        # Context
        self.typical_adr = config_dict['context']['typical_adr']
        self.correlation_instruments = config_dict['context']['correlation_instruments']
        self.correlation_weight = config_dict['context']['correlation_weight']
        
        # Sizing
        self.preferred_contract = config_dict['sizing']['preferred_contract']
        self.scale_to_mini_at_r = config_dict['sizing']['scale_to_mini_at_r']
    
    def __repr__(self) -> str:
        """String representation."""
        return f"InstrumentConfig({self.symbol} - {self.display_name})"


class InstrumentConfigLoader:
    """Load and manage instrument configurations."""
    
    def __init__(self, config_dir: Path = None):
        """Initialize loader."""
        if config_dir is None:
            config_dir = Path(__file__).parent / 'instruments'
        
        self.config_dir = config_dir
        self.configs: Dict[str, InstrumentConfig] = {}
        self._load_all()
    
    def _load_all(self):
        """Load all instrument configurations."""
        if not self.config_dir.exists():
            logger.warning(f"Instrument config directory not found: {self.config_dir}")
            return
        
        for yaml_file in self.config_dir.glob("*.yaml"):
            try:
                with open(yaml_file, 'r') as f:
                    config_dict = yaml.safe_load(f)
                
                symbol = config_dict['symbol']
                self.configs[symbol] = InstrumentConfig(config_dict)
                logger.info(f"Loaded config for {symbol}")
                
            except Exception as e:
                logger.error(f"Error loading {yaml_file.name}: {e}")
    
    def get(self, symbol: str) -> InstrumentConfig:
        """Get configuration for a symbol."""
        if symbol not in self.configs:
            raise ValueError(f"No configuration found for symbol: {symbol}")
        return self.configs[symbol]
    
    def get_all_symbols(self) -> list:
        """Get list of all configured symbols."""
        return list(self.configs.keys())
    
    def get_tradeable_instruments(self) -> Dict[str, InstrumentConfig]:
        """Get all tradeable instruments."""
        return self.configs.copy()


# Global loader instance
_loader = None


def get_instrument_config(symbol: str) -> InstrumentConfig:
    """Get instrument configuration (singleton pattern)."""
    global _loader
    if _loader is None:
        _loader = InstrumentConfigLoader()
    return _loader.get(symbol)


def get_all_instruments() -> Dict[str, InstrumentConfig]:
    """Get all instrument configurations."""
    global _loader
    if _loader is None:
        _loader = InstrumentConfigLoader()
    return _loader.get_tradeable_instruments()


def reset_loader():
    """Reset the global loader to force reload of configs."""
    global _loader
    _loader = None
