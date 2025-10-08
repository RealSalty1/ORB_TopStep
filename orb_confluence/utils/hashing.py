"""Configuration hashing for reproducibility."""

import hashlib
import json


def config_hash(config_dict: dict) -> str:
    """Generate hash of configuration for reproducibility tracking.

    Args:
        config_dict: Configuration dictionary.

    Returns:
        SHA256 hash (first 16 chars).
    """
    # Sort keys for consistent hashing
    config_json = json.dumps(config_dict, sort_keys=True)
    hash_obj = hashlib.sha256(config_json.encode())
    return hash_obj.hexdigest()[:16]
