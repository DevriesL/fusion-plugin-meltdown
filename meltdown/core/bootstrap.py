"""Dependency bootstrap: auto-install vendored packages on first run."""
import os
import sys
import subprocess

import adsk.core

ADDIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB_DIR = os.path.join(ADDIN_DIR, 'lib')
_MARKER = os.path.join(LIB_DIR, '.deps_installed')
_PACKAGE = 'pydantic-ai-slim[google,openai,anthropic]'


def ensure_dependencies() -> bool:
    """Check for vendored deps; install if missing. Returns True on success.

    Uses uv pip install --target (per D-01). Falls back to pip if uv is not
    on PATH. Targets macOS only for Phase 1 (per D-08).
    """
    if os.path.exists(_MARKER):
        _inject_lib_path()
        return True

    app = adsk.core.Application.get()
    ui = app.userInterface

    try:
        _install_with_uv()
    except FileNotFoundError:
        try:
            _install_with_pip()
        except Exception as e:
            ui.messageBox(
                f'Meltdown: Failed to install dependencies.\n\n'
                f'Error: {e}\n\n'
                f'Please install uv (https://docs.astral.sh/uv/) '
                f'and restart Fusion 360.',
                'Meltdown Setup Error'
            )
            return False
    except subprocess.CalledProcessError as e:
        ui.messageBox(
            f'Meltdown: Dependency installation failed.\n\n'
            f'Exit code: {e.returncode}\n\n'
            f'Try running manually:\n'
            f'uv pip install --target "{LIB_DIR}" "{_PACKAGE}"',
            'Meltdown Setup Error'
        )
        return False
    except Exception as e:
        ui.messageBox(
            f'Meltdown: Unexpected error during dependency install.\n\n'
            f'Error: {e}',
            'Meltdown Setup Error'
        )
        return False

    # Write marker file
    with open(_MARKER, 'w') as f:
        f.write('installed')

    _inject_lib_path()

    # Verify critical import
    try:
        import pydantic_ai
        return True
    except ImportError as e:
        ui.messageBox(
            f'Meltdown: Dependencies installed but import failed.\n\n'
            f'Error: {e}\n\n'
            f'This may indicate ABI incompatibility with Fusion\'s Python. '
            f'Check the Text Command window for details.',
            'Meltdown Import Error'
        )
        # Remove marker so next restart retries
        os.remove(_MARKER)
        return False


def _inject_lib_path():
    """Add vendored lib directory to sys.path if not already present."""
    if LIB_DIR not in sys.path:
        sys.path.insert(0, LIB_DIR)


def _expanded_env():
    """Build env dict with expanded PATH for macOS GUI apps.

    Fusion 360 launches as a GUI app with a minimal PATH (/usr/bin:/bin).
    Developer tools like uv live in locations not on this minimal PATH.
    """
    env = os.environ.copy()
    home = os.path.expanduser('~')
    extra = [
        os.path.join(home, '.local', 'bin'),
        os.path.join(home, '.cargo', 'bin'),
        '/usr/local/bin',
        '/opt/homebrew/bin',
    ]
    env['PATH'] = ':'.join(extra) + ':' + env.get('PATH', '')
    return env


def _install_with_uv():
    """Install dependencies using uv (preferred per D-01)."""
    subprocess.check_call(
        ['uv', 'pip', 'install', '--target', LIB_DIR, _PACKAGE],
        env=_expanded_env(),
        timeout=120
    )


def _install_with_pip():
    """Fallback: install using system python3 (not Fusion's sys.executable).

    Fusion's sys.executable points to the Fusion binary, not Python.
    Use system python3 with expanded PATH instead.
    """
    subprocess.check_call(
        ['python3', '-m', 'pip', 'install', '--target', LIB_DIR, _PACKAGE],
        env=_expanded_env(),
        timeout=120
    )
