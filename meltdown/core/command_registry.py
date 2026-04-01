"""Slash command registry: register, lookup, and execute commands.

Commands are registered by name with a description and handler callable.
The chatShow palette_incoming function consults this registry for every
message starting with '/'. Future phases (7-9) register additional
commands into this same registry.
"""

_commands = {}


def register(name, description, handler, show_in_menu=True):
    """Register a slash command.

    Arguments:
    name -- Command name without slash (e.g., 'clear').
    description -- Short description shown in dropdown menu.
    handler -- Callable(data, send_fn) invoked when command executes.
    show_in_menu -- Whether to include in the / dropdown menu.
    """
    _commands[name] = {
        'description': description,
        'handler': handler,
        'show_in_menu': show_in_menu,
    }


def execute(name, data=None, send_fn=None):
    """Execute a registered command. Returns True if found, False if not."""
    cmd = _commands.get(name)
    if cmd:
        cmd['handler'](data, send_fn)
        return True
    return False


def get_menu_commands():
    """Return list of {name, description} for commands visible in the / menu."""
    return [
        {'name': name, 'description': info['description']}
        for name, info in _commands.items()
        if info['show_in_menu']
    ]
