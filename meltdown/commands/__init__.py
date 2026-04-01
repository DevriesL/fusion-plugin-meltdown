# Meltdown command registry -- imports and lifecycle management for all commands.

from .commandDialog import entry as commandDialog
# paletteShow and paletteSend are sample commands replaced by chatShow
# from .paletteShow import entry as paletteShow
# from .paletteSend import entry as paletteSend
from .foundationTest import entry as foundationTest
from .agentTest import entry as agentTest
from .chatShow import entry as chatShow

commands = [
    commandDialog,
    foundationTest,
    agentTest,
    chatShow,
]


# Initialize all command modules (UI buttons, event handlers).
def start():
    for command in commands:
        command.start()


# Tear down all command modules (remove buttons, clear handlers).
def stop():
    for command in commands:
        command.stop()