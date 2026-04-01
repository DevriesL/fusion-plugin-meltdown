"""Multi-provider API key management: load, save, and ensure key availability.

Supports Gemini, Claude (Anthropic), and OpenAI provider API keys stored
separately in the .secrets JSON file. Backward-compatible with the original
single-key format (gemini_api_key).
"""
import json
import os

ADDIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRETS_PATH = os.path.join(ADDIN_DIR, '.secrets')

# Maps provider name to the environment variable PydanticAI expects
_PROVIDER_ENV_VARS = {
    'gemini': 'GOOGLE_API_KEY',
    'claude': 'ANTHROPIC_API_KEY',
    'openai': 'OPENAI_API_KEY',
}


def _load_secrets() -> dict:
    """Load the raw secrets dict from disk. Returns empty dict on failure."""
    if not os.path.exists(SECRETS_PATH):
        return {}
    try:
        with open(SECRETS_PATH, 'r') as f:
            return json.loads(f.read())
    except (json.JSONDecodeError, IOError):
        return {}


def load_api_key() -> str | None:
    """Load Gemini API key from .secrets file. Returns None if not found.

    Backward-compatible alias for load_provider_key('gemini').
    """
    return load_provider_key('gemini')


def save_api_key(api_key: str):
    """Save Gemini API key to .secrets file (gitignored per D-03).

    Backward-compatible alias for save_provider_key('gemini', api_key).
    """
    save_provider_key('gemini', api_key)


def load_provider_key(provider: str) -> str | None:
    """Load API key for a specific provider from .secrets file.

    Args:
        provider: One of 'gemini', 'claude', 'openai'.

    Returns:
        The API key string or None if not found.
    """
    secrets = _load_secrets()
    return secrets.get(f'{provider}_api_key')


def save_provider_key(provider: str, api_key: str):
    """Save API key for a specific provider, preserving other providers' keys.

    Args:
        provider: One of 'gemini', 'claude', 'openai'.
        api_key: The API key to store.
    """
    secrets = _load_secrets()
    secrets[f'{provider}_api_key'] = api_key
    with open(SECRETS_PATH, 'w') as f:
        f.write(json.dumps(secrets))


def load_all_keys() -> dict:
    """Return masked API keys for all providers (for UI display).

    Returns:
        Dict like {'gemini': '****abcd', 'claude': '', 'openai': '****efgh'}.
        Keys with >4 chars are masked as '****' + last 4 chars.
        Keys with 1-4 chars are masked as '****'.
        Missing keys return empty string.
    """
    secrets = _load_secrets()
    result = {}
    for provider in ('gemini', 'claude', 'openai'):
        key = secrets.get(f'{provider}_api_key', '')
        if key and len(key) > 4:
            result[provider] = '****' + key[-4:]
        elif key:
            result[provider] = '****'
        else:
            result[provider] = ''
    return result


def ensure_provider_key(provider: str) -> bool:
    """Load API key for provider and set the appropriate env var.

    Args:
        provider: One of 'gemini', 'claude', 'openai'.

    Returns:
        True if key is available and the env var was set.
    """
    key = load_provider_key(provider)
    if key:
        env_var = _PROVIDER_ENV_VARS.get(provider)
        if env_var:
            os.environ[env_var] = key
            return True
    return False


def ensure_api_key() -> bool:
    """Load Gemini API key and set GOOGLE_API_KEY env var.

    Backward-compatible alias for ensure_provider_key('gemini').
    Returns True if key is available and set.
    """
    return ensure_provider_key('gemini')
