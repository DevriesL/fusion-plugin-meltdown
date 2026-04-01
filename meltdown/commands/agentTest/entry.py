"""Meltdown: Agent Test command.

Phase 2 proof-of-concept: triggers the modeling agent with a hardcoded
CNC enclosure prompt to exercise the full tool chain:
- Modeling operations (sketch, extrude, shell, fillet, holes)
- Visual review (viewport screenshot + Gemini vision analysis)
- Transaction grouping (single Cmd+Z undoes all operations)
- Error self-correction (ModelRetry on failures)
- Text narration (agent logs what it's doing)

The agent runs on a worker thread. All Fusion API calls dispatch
through the bridge to the main thread.
"""
import threading
import traceback
import os

import adsk.core
from ...lib import fusionAddInUtils as futil
from ... import config

app = adsk.core.Application.get()
ui = app.userInterface

CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_AgentTest'
CMD_NAME = 'Meltdown: Test Agent'
CMD_Description = 'Run the modeling agent with a test CNC enclosure prompt'

WORKSPACE_ID = 'FusionSolidEnvironment'
PANEL_ID = 'SolidScriptsAddinsPanel'
COMMAND_BESIDE_ID = 'ScriptsManagerCommand'
IS_PROMOTED = True

ICON_FOLDER = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'resources', ''
)

local_handlers = []


def start():
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
    )
    futil.add_handler(cmd_def.commandCreated, command_created)

    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    control = panel.controls.addCommand(cmd_def, COMMAND_BESIDE_ID, False)
    control.isPromoted = IS_PROMOTED


def stop():
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    command_control = panel.controls.itemById(CMD_ID)
    command_definition = ui.commandDefinitions.itemById(CMD_ID)

    if command_control:
        command_control.deleteMe()
    if command_definition:
        command_definition.deleteMe()


def command_created(args: adsk.core.CommandCreatedEventArgs):
    futil.log(f'{CMD_NAME}: Command created event.')

    # No dialog inputs needed -- execute immediately on click
    futil.add_handler(
        args.command.execute, command_execute, local_handlers=local_handlers
    )
    futil.add_handler(
        args.command.destroy, command_destroy, local_handlers=local_handlers
    )


def command_execute(args: adsk.core.CommandEventArgs):
    """Starts the modeling agent on a worker thread."""
    futil.log(f'{CMD_NAME}: Command execute event. Starting agent thread.')

    # Check prerequisites before launching thread
    from ...core.secrets import ensure_api_key
    if not ensure_api_key():
        ui.messageBox(
            'No Gemini API key configured.\n\n'
            'Please use "Meltdown: Set API Key" command first.',
            'Meltdown: Agent Test'
        )
        return

    # Verify dependencies are available
    try:
        import pydantic_ai
        futil.log(f'{CMD_NAME}: pydantic_ai v{pydantic_ai.__version__} available')
    except ImportError as e:
        ui.messageBox(
            f'PydanticAI not available: {e}\n\n'
            f'Try restarting Fusion 360 to trigger dependency auto-install.',
            'Meltdown: Agent Test'
        )
        return

    thread = threading.Thread(target=_run_agent_test, daemon=True)
    thread.start()


def _run_agent_test():
    """Run the modeling agent with a CNC enclosure test prompt.

    Exercises: MODL-01 (NL -> model), MODL-02 (tools), MODL-05 (undo group),
    VISL-02 (visual review), and MODL-06 (error self-correction).
    """
    from ...core.bridge import dispatch_to_main_thread

    try:
        futil.log(f'{CMD_NAME}: Agent test thread started.')

        from ...core.agent import run_modeling_agent

        prompt = (
            'Create a simple CNC aluminum enclosure with these specifications:\n'
            '- Start with a 100mm x 60mm rectangle on the XY plane\n'
            '- Extrude it 40mm upward to create a solid box\n'
            '- Shell it with 2mm wall thickness, removing the top face to create an open-top enclosure\n'
            '- Fillet all top edges with 1mm radius for smooth edges\n'
            '- After you are done, use visual_review to check your work\n'
            '- Narrate each step as you go'
        )

        futil.log(f'{CMD_NAME}: Sending prompt to modeling agent...')
        result_text, _ = run_modeling_agent(prompt)
        futil.log(f'{CMD_NAME}: Agent response: {result_text[:300]}')

        summary = (
            '=== Meltdown Agent Test Results ===\n\n'
            'The modeling agent executed a CNC enclosure prompt.\n'
            'Check the Fusion 360 viewport for the created geometry.\n'
            'Check the timeline for a grouped "Meltdown:" entry.\n\n'
            '--- Agent Response ---\n\n'
            f'{result_text}'
        )
        dispatch_to_main_thread('show_result', {'message': summary})
        futil.log(f'{CMD_NAME}: Agent test complete.')

    except Exception as e:
        error_msg = (
            f'Agent test failed:\n\n'
            f'{type(e).__name__}: {e}\n\n'
            f'{traceback.format_exc()}'
        )
        futil.log(f'{CMD_NAME}: ERROR - {error_msg}',
                   adsk.core.LogLevels.ErrorLogLevel)
        try:
            dispatch_to_main_thread('show_error', {'message': error_msg})
        except Exception:
            futil.log(f'{CMD_NAME}: Could not display error via bridge.',
                       adsk.core.LogLevels.ErrorLogLevel)


def command_destroy(args: adsk.core.CommandEventArgs):
    futil.log(f'{CMD_NAME}: Command destroy event.')
    global local_handlers
    local_handlers = []
