"""Logging configuration."""

import sys
from pathlib import Path

from loguru import logger


def setup_logging(level: str = "INFO", log_file: Path | None = None) -> None:
    """Setup loguru logging.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR).
        log_file: Optional log file path.
    """
    # Remove default handler
    logger.remove()

    # Add console handler
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=level,
        colorize=True,
    )

    # Add file handler if specified
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_file,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level=level,
            rotation="10 MB",
            retention="30 days",
        )
