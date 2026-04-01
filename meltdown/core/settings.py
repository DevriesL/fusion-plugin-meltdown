"""User-configurable settings: load, save, and get with defaults fallback.

Settings are stored in a .settings JSON file in the add-in directory.
On first run (no file), all values come from _DEFAULTS which mirror
the hardcoded constants in config.py. The config overlay (plan 02)
writes through save(), and agent.py reads through get().
"""
import json
import os

ADDIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_PATH = os.path.join(ADDIN_DIR, '.settings')

# Defaults match current config.py hardcoded values
_DEFAULTS = {
    'ai_provider': 'gemini',
    'ai_model_name': 'gemini-3.1-pro-preview',
    'max_visual_iterations': 5,
    'viewport_capture_width': 1920,
    'viewport_capture_height': 1080,
    'agent_dispatch_timeout': 60,
    'visual_review_angles': ['front', 'right', 'top', 'iso'],
    'debug': True,
}

_cache = None  # In-memory cache, loaded once


def load():
    """Load settings from disk, merge with defaults. Returns settings dict."""
    global _cache
    settings = dict(_DEFAULTS)
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, 'r') as f:
                stored = json.loads(f.read())
            settings.update(stored)
        except (json.JSONDecodeError, IOError):
            pass  # Fall back to defaults on corrupt/missing file
    _cache = settings
    return settings


def save(settings):
    """Write settings dict to disk and update cache."""
    global _cache
    with open(SETTINGS_PATH, 'w') as f:
        f.write(json.dumps(settings, indent=2))
    _cache = dict(settings)


def get(key, default=None):
    """Get a setting value from cache, loading from disk if needed."""
    global _cache
    if _cache is None:
        load()
    return _cache.get(key, default if default is not None else _DEFAULTS.get(key))
