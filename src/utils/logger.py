"""Logging utilities for PLM"""
import logging
import sys
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.logging import RichHandler

console = Console()

def setup_logger(name: str, log_file: str = None, level: str = "INFO") -> logging.Logger:
    """Setup logger with console and file handlers"""

    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    logger.handlers = []

    # Console handler (rich)
    console_handler = RichHandler(
        console=console,
        show_time=True,
        show_path=False,
        markup=True
    )
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)

    # File handler
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)

        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger

def get_logger(name: str) -> logging.Logger:
    """Get or create logger"""
    return logging.getLogger(name)
