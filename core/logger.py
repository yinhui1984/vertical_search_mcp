"""
Logging system for vertical search MCP.

This module provides a centralized logging configuration that:
- Outputs to both file (with rotation) and stderr (for Claude Desktop capture)
- Supports different log levels (DEBUG, INFO, WARNING, ERROR)
- Formats logs with timestamp, level, module name, and message
- Provides RollingConsoleHandler for CLI with fixed-line display
"""

import logging
import sys
import shutil
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, List


def setup_logger(
    name: str = "vertical_search",
    log_file: Optional[str] = None,
    log_level: int = logging.INFO,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    use_rolling_console: bool = False,
    rolling_console_lines: int = 4,
    force_reconfigure: bool = False,
) -> logging.Logger:
    """
    Setup and configure logger with file and console handlers.

    This function configures a logger that:
    1. Writes to a file with rotation (RotatingFileHandler) - ALWAYS full logging
    2. Writes to stderr with either:
       - Standard StreamHandler (for MCP server, Claude Desktop)
       - RollingConsoleHandler (for CLI, fixed-line display)
    3. Uses consistent formatting across all handlers

    Args:
        name: Logger name (default: "vertical_search")
        log_file: Path to log file (default: "logs/vertical_search.log")
        log_level: Logging level (default: INFO)
        max_bytes: Maximum log file size before rotation (default: 10MB)
        backup_count: Number of backup files to keep (default: 5)
        use_rolling_console: Use RollingConsoleHandler for stderr (default: False)
        rolling_console_lines: Number of lines for rolling console (default: 4)
        force_reconfigure: Force reconfiguration even if handlers exist (default: False)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Avoid adding handlers multiple times (unless force_reconfigure is True)
    if logger.handlers and not force_reconfigure:
        return logger
    
    # If force_reconfigure, remove existing handlers
    if force_reconfigure and logger.handlers:
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)

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

    # Console handler (stderr)
    # Choose between standard StreamHandler or RollingConsoleHandler
    if use_rolling_console:
        # Use RollingConsoleHandler for CLI (fixed-line display)
        console_handler = RollingConsoleHandler(
            max_lines=rolling_console_lines,
            min_level=log_level,
            show_timestamp=False,  # Cleaner display without timestamps
        )
        # RollingConsoleHandler does its own formatting
    else:
        # Standard StreamHandler for MCP server / Claude Desktop
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


class RollingConsoleHandler(logging.Handler):
    """
    Console handler that maintains a fixed-size rolling window of log messages.
    
    Uses ANSI escape sequences to update a fixed number of lines in place,
    providing a clean, non-scrolling log display for CLI applications.
    
    Features:
    - Fixed display area (configurable number of lines)
    - Automatic text truncation for long messages
    - Color-coded log levels
    - Timestamp display
    - Rolling buffer (oldest messages are removed)
    """
    
    # ANSI color codes for log levels
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
    }
    RESET = '\033[0m'
    GRAY = '\033[90m'
    
    def __init__(
        self,
        max_lines: int = 4,
        min_level: int = logging.DEBUG,
        show_timestamp: bool = False,
    ):
        """
        Initialize RollingConsoleHandler.
        
        Args:
            max_lines: Maximum number of lines to display (default: 4)
            min_level: Minimum log level to display (default: DEBUG)
            show_timestamp: Whether to show timestamp (default: False for cleaner display)
        """
        super().__init__()
        self.max_lines = max_lines
        self.min_level = min_level
        self.show_timestamp = show_timestamp
        self.log_buffer: List[str] = []
        self.initialized = False
        self.terminal_width = self._get_terminal_width()
    
    def _get_terminal_width(self) -> int:
        """Get terminal width, with fallback."""
        try:
            size = shutil.get_terminal_size(fallback=(80, 24))
            return size.columns
        except Exception:
            return 80
    
    def _truncate_message(self, message: str, max_length: int) -> str:
        """
        Truncate message to fit terminal width.
        
        Args:
            message: Message to truncate
            max_length: Maximum length
            
        Returns:
            Truncated message with ellipsis if needed
        """
        if len(message) <= max_length:
            return message
        return message[:max_length - 3] + "..."
    
    def _format_log_line(self, record: logging.LogRecord) -> str:
        """
        Format a log record for display.
        
        Args:
            record: Log record to format
            
        Returns:
            Formatted string with colors and truncation
        """
        # Get color for log level
        level_name = record.levelname
        color = self.COLORS.get(level_name, self.RESET)
        
        # Build message parts
        parts = []
        
        # Timestamp (optional)
        if self.show_timestamp:
            timestamp = self.formatTime(record, "%H:%M:%S")
            parts.append(f"{self.GRAY}{timestamp}{self.RESET}")
        
        # Level name with color
        parts.append(f"{color}[{level_name:^8}]{self.RESET}")
        
        # Module name (shortened)
        module = record.filename.replace('.py', '')
        parts.append(f"{self.GRAY}{module}{self.RESET}")
        
        # Message
        parts.append(record.getMessage())
        
        # Join and truncate
        full_message = " ".join(parts)
        
        # Calculate available width (leaving some margin)
        available_width = self.terminal_width - 2
        
        return self._truncate_message(full_message, available_width)
    
    def emit(self, record: logging.LogRecord) -> None:
        """
        Process a log record and update the display.
        
        Args:
            record: Log record to emit
        """
        try:
            # Filter by level
            if record.levelno < self.min_level:
                return
            
            # Format the message
            formatted_message = self._format_log_line(record)
            
            # Add to buffer (rolling window)
            self.log_buffer.append(formatted_message)
            if len(self.log_buffer) > self.max_lines:
                self.log_buffer.pop(0)
            
            # Update display
            self._update_display()
            
        except Exception:
            self.handleError(record)
    
    def _update_display(self) -> None:
        """Update the console display with current buffer."""
        if not self.initialized:
            # First time: reserve space for our log lines
            sys.stderr.write("\n" * self.max_lines)
            sys.stderr.flush()
            self.initialized = True
        
        # Move cursor up to the start of our log area
        sys.stderr.write(f"\033[{self.max_lines}A")
        
        # Clear and rewrite each line
        for i in range(self.max_lines):
            # Move to start of line and clear it
            sys.stderr.write("\r\033[K")
            
            # Write log message if we have one for this line
            if i < len(self.log_buffer):
                sys.stderr.write(self.log_buffer[i])
            
            # Move to next line (except for the last one)
            if i < self.max_lines - 1:
                sys.stderr.write("\n")
        
        # Move cursor to end of our area
        sys.stderr.write("\n")
        sys.stderr.flush()
    
    def close(self) -> None:
        """Cleanup on close - ensure cursor is positioned correctly."""
        if self.initialized:
            # Ensure we're at the end of our display area
            sys.stderr.write("\n")
            sys.stderr.flush()
        super().close()


def get_logger(name: str = "vertical_search") -> logging.Logger:
    """
    Get or create a logger instance.

    If logger is not configured, it will be set up with default settings.
    For child loggers (e.g., "vertical_search.cli"), they will propagate to
    the parent logger instead of creating separate handlers.

    Args:
        name: Logger name (default: "vertical_search")

    Returns:
        Logger instance
    """
    logger = logging.getLogger(name)

    # For child loggers (with dots), let them propagate to parent
    # Only configure the root "vertical_search" logger
    if "." in name:
        # This is a child logger, ensure parent is configured
        parent_name = name.split(".")[0]
        parent_logger = logging.getLogger(parent_name)
        if not parent_logger.handlers:
            setup_logger(name=parent_name)
        # Child loggers should propagate to parent
        logger.propagate = True
        return logger

    # For the root logger, set it up if not already configured
    if not logger.handlers:
        setup_logger(name=name)

    return logger
