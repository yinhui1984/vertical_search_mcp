#!/usr/bin/env python3
"""
Quick test to verify rolling console handler works in CLI context.
"""

import sys
import logging
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.logger import setup_logger, get_logger

# Simulate what happens in CLI
print("Step 1: Configure logger with rolling console (simulating main_async)")
setup_logger(
    name="vertical_search",
    log_level=logging.INFO,
    use_rolling_console=True,
    rolling_console_lines=4,
    force_reconfigure=True,
)

print("Step 2: Get child logger (simulating CLI.__init__)")
logger = get_logger("vertical_search.cli")

print("Step 3: Check logger configuration")
parent_logger = logging.getLogger("vertical_search")
print(f"  Parent logger 'vertical_search' handlers: {parent_logger.handlers}")
print(f"  Child logger 'vertical_search.cli' handlers: {logger.handlers}")
print(f"  Child logger propagate: {logger.propagate}")

print("\nStep 4: Emit some test logs")
print("(You should see them in a fixed 4-line window below)\n")

import time
logger.info("Test message 1")
time.sleep(0.3)
logger.info("Test message 2")
time.sleep(0.3)
logger.debug("Test message 3 (DEBUG - may not show if log level is INFO)")
time.sleep(0.3)
logger.info("Test message 4")
time.sleep(0.3)
logger.info("Test message 5 - should push out message 1")
time.sleep(0.3)
logger.warning("Test WARNING")
time.sleep(0.3)
logger.error("Test ERROR")
time.sleep(0.3)
logger.info("Test message 8")
time.sleep(0.5)

print("\n" + "="*60)
print("If you saw a fixed 4-line window above, it's working!")
print("="*60)
