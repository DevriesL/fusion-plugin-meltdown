# Assuming you have not changed the general structure of the template no modification is needed in this file.
from . import commands
from .lib import fusionAddInUtils as futil


def run(context):
    try:
        # Bootstrap vendored dependencies before any command imports that need them
        from .core.bootstrap import ensure_dependencies
        deps_ok = ensure_dependencies()

        if deps_ok:
            # Load API key into environment if available
            from .core.secrets import ensure_api_key
            ensure_api_key()

            # Set up the main-thread dispatch bridge
            from .core.bridge import setup_bridge
            setup_bridge()

        # Start commands even if deps failed -- apiKeyManager still works
        # and user can set API key. Foundation test will report dep failure.
        commands.start()

    except:
        futil.handle_error('run')


def stop(context):
    try:
        # Remove all of the event handlers your app has created
        futil.clear_handlers()

        # Tear down the bridge before stopping commands
        try:
            from .core.bridge import teardown_bridge
            teardown_bridge()
        except Exception:
            pass  # Best-effort during shutdown

        # This will run the start function in each of your commands as defined in commands/__init__.py
        commands.stop()

    except:
        futil.handle_error('stop')