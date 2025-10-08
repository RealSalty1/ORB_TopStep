"""Configuration loader with YAML merging and hashing."""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger
from ruamel.yaml import YAML

from .schema import StrategyConfig


def deep_merge(base: Dict, override: Dict) -> Dict:
    """Deep merge two dictionaries (override takes precedence).

    Args:
        base: Base dictionary.
        override: Override dictionary.

    Returns:
        Merged dictionary.
    """
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value

    return result


def load_yaml(path: Path) -> Dict[str, Any]:
    """Load YAML file to dict.

    Args:
        path: Path to YAML file.

    Returns:
        Dictionary with YAML contents.

    Raises:
        FileNotFoundError: If file doesn't exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"YAML file not found: {path}")

    yaml = YAML(typ="safe")
    with path.open("r") as f:
        data = yaml.load(f)

    return data if data is not None else {}


def load_config(
    path: Optional[Path | str] = None,
    use_defaults: bool = True,
) -> StrategyConfig:
    """Load strategy configuration with optional defaults merging.

    Args:
        path: Path to user configuration file. If None, loads defaults only.
        use_defaults: Whether to merge with defaults.yaml.

    Returns:
        Validated StrategyConfig instance.

    Raises:
        FileNotFoundError: If config file doesn't exist.
        ValueError: If config validation fails.
    """
    config_dir = Path(__file__).parent
    defaults_path = config_dir / "defaults.yaml"

    # Load defaults
    if use_defaults and defaults_path.exists():
        raw_config = load_yaml(defaults_path)
        logger.debug("Loaded defaults configuration")
    else:
        raw_config = {}

    # Load user config and merge
    if path is not None:
        path = Path(path)
        user_config = load_yaml(path)
        raw_config = deep_merge(raw_config, user_config)
        logger.debug(f"Merged user configuration from {path}")

    # Validate with pydantic
    try:
        config = StrategyConfig(**raw_config)
        logger.info(f"Loaded configuration: {config.name} v{config.version}")
        return config
    except Exception as e:
        raise ValueError(f"Config validation failed: {e}") from e


def get_default_config() -> Path:
    """Get path to default configuration file.

    Returns:
        Path to defaults.yaml.

    Raises:
        FileNotFoundError: If defaults.yaml not found.
    """
    config_dir = Path(__file__).parent
    default_path = config_dir / "defaults.yaml"

    if not default_path.exists():
        raise FileNotFoundError(f"Default config not found: {default_path}")

    return default_path


def resolved_config_hash(config: StrategyConfig) -> str:
    """Generate stable hash of configuration for reproducibility.

    Uses canonical JSON serialization to ensure consistent hashing.

    Args:
        config: StrategyConfig instance.

    Returns:
        SHA256 hash (first 16 characters).
    """
    # Convert to dict
    config_dict = config.model_dump(mode="json")

    # Canonicalize: sort keys, no whitespace, stable formatting
    canonical_json = json.dumps(
        config_dict,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )

    # Hash
    hash_obj = hashlib.sha256(canonical_json.encode("utf-8"))
    config_hash = hash_obj.hexdigest()[:16]

    logger.debug(f"Config hash: {config_hash}")

    return config_hash


def save_config(config: StrategyConfig, path: Path) -> None:
    """Save configuration to YAML file.

    Args:
        config: StrategyConfig to save.
        path: Output path.
    """
    config_dict = config.model_dump(mode="json")

    yaml = YAML()
    yaml.default_flow_style = False

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w") as f:
        yaml.dump(config_dict, f)

    logger.info(f"Saved configuration to {path}")