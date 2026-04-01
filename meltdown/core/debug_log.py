"""Debug log relay: dispatches structured log entries to the chat palette.

Provides a central point for all log sources (agent lifecycle, tool calls,
bridge dispatch, futil.log output) to send entries to the debug panel UI.

The dispatch function is set during palette startup and cleared on
palette close / add-in shutdown. When no dispatch is configured, all
calls are silently ignored (zero overhead when debug panel is inactive).
"""
import datetime

# Module-level state
_dispatch_fn = None

# Level mapping from string representations to standard labels
_LEVEL_MAP = {
    'info': 'INFO',
    'error': 'ERROR',
    'debug': 'DEBUG',
    'warn': 'WARN',
}


def set_dispatch(fn):
    """Set the dispatch function for relaying log entries to the palette.

    Called once during palette setup to enable log relay.

    Args:
        fn: Callable that accepts a payload dict with keys:
            action, timestamp, level, source, message.
    """
    global _dispatch_fn
    _dispatch_fn = fn


def clear_dispatch():
    """Clear the dispatch function, disabling log relay.

    Called on palette close or add-in shutdown.
    """
    global _dispatch_fn
    _dispatch_fn = None


def dispatch_log(message, level='INFO', source='system'):
    """Dispatch a structured log entry to the debug panel.

    If no dispatch function is configured (panel not active), returns
    immediately with zero overhead.

    Args:
        message: The log message string.
        level: Severity level -- 'DEBUG', 'INFO', 'WARN', or 'ERROR'.
        source: Log source -- 'agent', 'tool', 'bridge', or 'system'.
    """
    if _dispatch_fn is None:
        return

    payload = {
        'action': 'debug_log',
        'timestamp': datetime.datetime.now().isoformat(timespec='milliseconds'),
        'level': level,
        'source': source,
        'message': str(message),
    }

    try:
        _dispatch_fn(payload)
    except Exception:
        pass  # Log relay must never crash the app


def log_hook(message, level_str):
    """Hook function called by the modified futil.log().

    Maps the Fusion log level string to standard levels and dispatches
    to the debug panel.

    Args:
        message: The log message from futil.log().
        level_str: String representation of the Fusion log level.
    """
    level_lower = level_str.lower()
    if 'error' in level_lower:
        mapped_level = 'ERROR'
    elif 'warn' in level_lower:
        mapped_level = 'WARN'
    elif 'debug' in level_lower:
        mapped_level = 'DEBUG'
    else:
        mapped_level = 'INFO'

    dispatch_log(message, level=mapped_level, source='system')
