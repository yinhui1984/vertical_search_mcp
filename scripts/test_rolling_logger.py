#!/usr/bin/env python3
"""
Test script for RollingConsoleHandler.

This script demonstrates the rolling log display with fixed lines.
It simulates a typical search workflow with various log messages.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.logger import setup_logger, get_logger


async def simulate_search_workflow():
    """Simulate a search workflow with various log messages."""
    
    # Setup logger with rolling console
    setup_logger(
        name="test_rolling",
        log_level=logging.DEBUG,
        use_rolling_console=True,
        rolling_console_lines=4,
    )
    
    logger = get_logger("test_rolling")
    
    print("=" * 60)
    print("Testing Rolling Console Handler")
    print("=" * 60)
    print("\nYou should see a fixed 4-line log display below:")
    print("(Watch how old messages roll off as new ones arrive)\n")
    
    # Wait a bit for the display to initialize
    await asyncio.sleep(0.5)
    
    # Simulate search workflow
    steps = [
        (logging.INFO, "Initializing search manager..."),
        (logging.DEBUG, "Registering platforms: weixin, google, zhihu"),
        (logging.INFO, "Starting search for: Python async programming"),
        (logging.DEBUG, "Cache miss - fetching fresh results"),
        (logging.INFO, "Searching WeChat articles..."),
        (logging.DEBUG, "Found 5 articles from WeChat"),
        (logging.INFO, "Fetching article content (1/5)..."),
        (logging.DEBUG, "Content length: 12345 chars"),
        (logging.INFO, "Fetching article content (2/5)..."),
        (logging.DEBUG, "Content length: 8901 chars"),
        (logging.WARNING, "Rate limit approaching, slowing down..."),
        (logging.INFO, "Fetching article content (3/5)..."),
        (logging.DEBUG, "Content length: 15678 chars"),
        (logging.INFO, "Compressing content with LLM..."),
        (logging.DEBUG, "Compression ratio: 45%"),
        (logging.INFO, "Fetching article content (4/5)..."),
        (logging.DEBUG, "Content length: 10234 chars"),
        (logging.INFO, "Fetching article content (5/5)..."),
        (logging.DEBUG, "Content length: 9876 chars"),
        (logging.INFO, "All content fetched successfully"),
        (logging.INFO, "Summarizing articles concurrently..."),
        (logging.DEBUG, "Summarized article 1: 'Python异步编程入门'"),
        (logging.DEBUG, "Summarized article 2: 'AsyncIO实战指南'"),
        (logging.DEBUG, "Summarized article 3: '异步协程深度解析'"),
        (logging.DEBUG, "Summarized article 4: 'Python并发编程技巧'"),
        (logging.DEBUG, "Summarized article 5: '异步编程最佳实践'"),
        (logging.INFO, "Search completed: 5 results found"),
        (logging.DEBUG, "Total execution time: 3.45s"),
    ]
    
    # Emit logs with delays to show rolling effect
    for level, message in steps:
        logger.log(level, message)
        await asyncio.sleep(0.3)  # Delay to observe rolling
    
    # Final message
    await asyncio.sleep(0.5)
    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)
    print("\nNote: The log file still contains ALL log messages.")
    print("Only the console display is limited to 4 lines.")


async def test_error_handling():
    """Test error and warning messages."""
    logger = get_logger("test_rolling")
    
    print("\n" + "=" * 60)
    print("Testing Error Messages")
    print("=" * 60)
    print()
    
    await asyncio.sleep(0.5)
    
    logger.warning("This is a warning message")
    await asyncio.sleep(0.5)
    
    logger.error("This is an error message")
    await asyncio.sleep(0.5)
    
    logger.critical("This is a critical message")
    await asyncio.sleep(0.5)
    
    logger.info("Back to normal operations")
    await asyncio.sleep(0.5)


async def main():
    """Main entry point."""
    try:
        await simulate_search_workflow()
        await test_error_handling()
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
