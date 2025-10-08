"""Logging configuration using loguru.

Provides structured logging with JSON support and automatic log rotation.
"""

import sys
from pathlib import Path
from typing import Optional

from loguru import logger


def setup_logger(
    log_level: str = "INFO",
    log_to_file: bool = True,
    log_dir: Path = Path("logs"),
    run_id: Optional[str] = None,
    serialize: bool = False,
) -> None:
    """Configure loguru logger with console and optional file output.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR).
        log_to_file: Whether to write logs to file.
        log_dir: Directory for log files.
        run_id: Optional run identifier for log filename.
        serialize: Whether to use JSON serialization for logs.
    """
    # Remove default handler
    logger.remove()

    # Add console handler with formatting
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=log_level,
        colorize=True,
    )

    # Add file handler if requested
    if log_to_file:
        log_dir.mkdir(parents=True, exist_ok=True)
        
        filename = "orb_strategy"
        if run_id:
            filename = f"{filename}_{run_id}"
        
        log_path = log_dir / f"{filename}.log"
        
        logger.add(
            log_path,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
            level=log_level,
            rotation="10 MB",
            retention="30 days",
            compression="zip",
            serialize=serialize,
        )
