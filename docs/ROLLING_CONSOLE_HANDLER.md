# Rolling Console Handler

## Overview

`RollingConsoleHandler` is a custom logging handler that provides a clean, fixed-line display for CLI applications. Instead of scrolling through endless log messages, it maintains a fixed "window" of the most recent log entries.

## Features

- ✅ **Fixed Display Area**: Shows only the last N log messages (default: 4 lines)
- ✅ **Color-Coded Levels**: Different colors for DEBUG, INFO, WARNING, ERROR, CRITICAL
- ✅ **Auto-Truncation**: Long messages are automatically truncated to fit terminal width
- ✅ **Rolling Buffer**: Oldest messages automatically removed as new ones arrive
- ✅ **File Logging Unaffected**: Complete logs are still written to file
- ✅ **ANSI Escape Sequences**: Uses standard terminal controls (no external dependencies)
- ✅ **Performance**: Minimal overhead, won't freeze or hang

## Visual Example

```
┌─────────────────────────────────────────────┐
│ [ INFO  ] cli Starting search...            │
│ [ DEBUG ] search_manager Cache miss         │
│ [ INFO  ] weixin_searcher Found 5 results   │
│ [ DEBUG ] content_fetcher Fetching (1/5)... │
└─────────────────────────────────────────────┘
```

As new logs arrive, the oldest line scrolls off the top.

## Usage

### In CLI Applications

```python
from core.logger import setup_logger

# Enable rolling console handler
setup_logger(
    name="vertical_search",
    log_level=logging.INFO,
    use_rolling_console=True,      # Enable fixed-line display
    rolling_console_lines=4,        # Number of lines to show
)
```

### In MCP Server

```python
from core.logger import setup_logger

# Use standard console handler (default)
setup_logger(
    name="vertical_search",
    log_level=logging.INFO,
    use_rolling_console=False,      # Standard scrolling logs
)
```

## Configuration Options

### `setup_logger()` Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | str | "vertical_search" | Logger name |
| `log_level` | int | `logging.INFO` | Minimum log level |
| `use_rolling_console` | bool | `False` | Enable rolling console display |
| `rolling_console_lines` | int | `4` | Number of lines in fixed window |
| `log_file` | str | auto | Path to log file |
| `max_bytes` | int | 10MB | Max log file size before rotation |
| `backup_count` | int | 5 | Number of backup files |

### `RollingConsoleHandler` Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_lines` | int | `4` | Fixed window size |
| `min_level` | int | `logging.DEBUG` | Minimum level to display |
| `show_timestamp` | bool | `False` | Show HH:MM:SS timestamps |

## How It Works

### 1. **ANSI Escape Sequences**

The handler uses standard ANSI terminal control sequences:
- `\033[NA` - Move cursor up N lines
- `\033[K` - Clear current line
- `\r` - Return to start of line

### 2. **Rolling Buffer**

```python
# Internal buffer maintains last N messages
log_buffer = [
    "[INFO] Message 1",
    "[DEBUG] Message 2",
    "[INFO] Message 3",
    "[DEBUG] Message 4",  # Most recent
]

# When new message arrives:
# - Pop oldest (Message 1)
# - Append newest (Message 5)
```

### 3. **Display Update**

Each time a log message is emitted:
1. Add to buffer (remove oldest if full)
2. Move cursor to start of display area
3. Clear and rewrite all lines
4. Flush output

## Benefits Over Other Solutions

### vs. Rich Library

| Feature | RollingConsoleHandler | Rich.Live |
|---------|----------------------|-----------|
| Dependencies | None (stdlib only) | Requires `rich` |
| Async-Safe | ✅ Yes | ⚠️ Needs careful handling |
| Performance | ✅ Fast | ⚠️ Can be slow/freeze |
| Simplicity | ✅ Simple | ❌ Complex |
| File Logging | ✅ Unaffected | ⚠️ Needs separate setup |

### vs. Simple Filtering

| Feature | RollingConsoleHandler | Level Filtering |
|---------|----------------------|-----------------|
| Show Recent Logs | ✅ Yes | ❌ No |
| Fixed Display | ✅ Yes | ❌ No |
| Debug Visibility | ✅ Visible (last N) | ❌ Hidden |

## Testing

Test the rolling console handler:

```bash
# Run test script
python scripts/test_rolling_logger.py

# Run actual CLI with rolling logs
python -m cli.cli "test query" --verbose
```

## File Logging

**Important**: The rolling console handler ONLY affects what you see on screen. All log messages (including those that scroll off) are still written to the log file in full detail.

Log file location:
- Primary: `{project_root}/logs/vertical_search.log`
- Fallback: `~/.vertical_search_mcp/logs/vertical_search.log`

## Limitations

1. **Terminal Compatibility**: Requires ANSI-compatible terminal (most modern terminals)
2. **Single Line Messages**: Multi-line messages are truncated to single line
3. **Window Resize**: Doesn't dynamically update on terminal resize (use initial width)
4. **Not for Piping**: When output is redirected, falls back to standard handler

## Implementation Details

### Color Codes

```python
COLORS = {
    'DEBUG': '\033[36m',      # Cyan
    'INFO': '\033[32m',       # Green
    'WARNING': '\033[33m',    # Yellow
    'ERROR': '\033[31m',      # Red
    'CRITICAL': '\033[35m',   # Magenta
}
```

### Log Format

Without timestamp:
```
[LEVEL   ] module message
```

With timestamp:
```
HH:MM:SS [LEVEL   ] module message
```

## Future Enhancements

Possible improvements:
- [ ] Dynamic terminal resize detection
- [ ] Configurable color schemes
- [ ] Multi-line message support
- [ ] Progress bar integration
- [ ] Mouse scrolling in supported terminals

## Troubleshooting

### Logs Not Displaying

**Problem**: No logs visible
**Solution**: Check `min_level` parameter matches your log levels

### Display Corruption

**Problem**: Jumbled display
**Solution**: Terminal may not support ANSI codes - use `use_rolling_console=False`

### Logs Disappear Too Quickly

**Problem**: Can't read fast-moving logs
**Solution**: Increase `rolling_console_lines` from 4 to 6 or 8

### Want to See All Logs

**Problem**: Need to see complete log history
**Solution**: Check the log file - it contains everything

## Related Files

- `core/logger.py` - Implementation
- `cli/cli.py` - CLI integration
- `scripts/test_rolling_logger.py` - Test script
