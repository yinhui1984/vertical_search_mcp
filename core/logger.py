"""
Logging system for vertical search MCP.

This module provides a centralized logging configuration that:
- Outputs to both file (with rotation) and stderr (for Claude Desktop capture)
- Supports different log levels (DEBUG, INFO, WARNING, ERROR)
- Formats logs with timestamp, level, module name, and message
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


def setup_logger(
    name: str = "vertical_search",
    log_file: Optional[str] = None,
    log_level: int = logging.INFO,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
) -> logging.Logger:
    """
    Setup and configure logger with file and console handlers.

    This function configures a logger that:
    1. Writes to a file with rotation (RotatingFileHandler)
    2. Writes to stderr (StreamHandler) - captured by Claude Desktop
    3. Uses consistent formatting across all handlers

    Args:
        name: Logger name (default: "vertical_search")
        log_file: Path to log file (default: "logs/vertical_search.log")
        log_level: Logging level (default: INFO)
        max_bytes: Maximum log file size before rotation (default: 10MB)
        backup_count: Number of backup files to keep (default: 5)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger

    logger.setLevel(log_level)

    # Determine log file path
    if log_file is None:
        # Try to use project root directory (where mcp_server.py is located)
        # Fallback to user home directory if project root is not writable
        project_root = Path(__file__).parent.parent.absolute()
        user_home = Path.home()
        
        log_file = None
        # Try project root first
        log_dir = project_root / "logs"
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            # Verify we can write to the directory
            test_file = log_dir / ".test_write"
            test_file.touch()
            test_file.unlink()
            # Successfully created and can write, use this location
            log_file = str(log_dir / "vertical_search.log")
        except (OSError, PermissionError):
            # Can't write to project root, try user home
            log_dir = user_home / ".vertical_search_mcp" / "logs"
            try:
                log_dir.mkdir(parents=True, exist_ok=True)
                # Verify we can write to the directory
                test_file = log_dir / ".test_write"
                test_file.touch()
                test_file.unlink()
                # Successfully created and can write, use this location
                log_file = str(log_dir / "vertical_search.log")
            except (OSError, PermissionError):
                # Can't create any directory or write, skip file logging
                # Will only use stderr output (captured by Claude Desktop)
                log_file = None

    # File handler with rotation (only if we have a valid log file path)
    file_handler = None
    if log_file:
        try:
            # Ensure directory exists for the log file
            log_path = Path(log_file)
            if log_path.parent != log_path:  # Not root directory
                try:
                    log_path.parent.mkdir(parents=True, exist_ok=True)
                except (OSError, PermissionError):
                    # Can't create directory, skip file logging
                    log_file = None
            
            if log_file:
                file_handler = RotatingFileHandler(
                    log_file,
                    maxBytes=max_bytes,
                    backupCount=backup_count,
                    encoding="utf-8",
                )
                file_handler.setLevel(log_level)
                file_formatter = logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
                file_handler.setFormatter(file_formatter)
        except (OSError, PermissionError):
            # Can't create file handler, skip file logging
            file_handler = None

    # Console handler (stderr) - captured by Claude Desktop
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_formatter)

    # Add handlers to logger
    if file_handler:
        logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # Prevent propagation to root logger
    logger.propagate = False

    return logger


def get_logger(name: str = "vertical_search") -> logging.Logger:
    """
    Get or create a logger instance.

    If logger is not configured, it will be set up with default settings.

    Args:
        name: Logger name (default: "vertical_search")

    Returns:
        Logger instance
    """
    logger = logging.getLogger(name)

    # If logger is not configured, set it up with defaults
    if not logger.handlers:
        setup_logger(name=name)

    return logger

