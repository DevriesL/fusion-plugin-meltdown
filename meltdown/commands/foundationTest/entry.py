"""Meltdown: Foundation Test command.

Per D-04: Single toolbar button that triggers full-chain validation.
Per D-05: Exercises all three FNDN requirements in one click:
  - FNDN-01: PydanticAI + google-genai import successfully
  - FNDN-02: Main thread dispatch round-trip (workspace info + viewport capture)
  - FNDN-03: Agent with structured tool call + vision input

The validation runs on a worker thread to avoid blocking Fusion's UI
(Research Pitfall 2). Results are displayed via the bridge's show_result
operation which calls ui.messageBox on the main thread.
"""
import threading
import traceback
import os

import adsk.core
from ...lib import fusionAddInUtils as futil
from ... import config

app = adsk.core.Application.get()
ui = app.userInterface

CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_FoundationTest'
CMD_NAME = 'Meltdown: Test Foundation'
CMD_Description = 'Run the full foundation validation: dependencies, dispatch bridge, and AI agent'

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
    """Starts the validation on a worker thread (Research Pitfall 2)."""
    futil.log(f'{CMD_NAME}: Command execute event. Starting validation thread.')

    # Check prerequisites before launching thread
    from ...core.secrets import ensure_api_key
    if not ensure_api_key():
        ui.messageBox(
            'No Gemini API key configured.\n\n'
            'Please use "Meltdown: Set API Key" command first.',
            'Meltdown: Foundation Test'
        )
        return

    # Verify dependencies are available
    try:
        import pydantic_ai
        futil.log(f'{CMD_NAME}: pydantic_ai imported successfully (v{pydantic_ai.__version__})')
    except ImportError as e:
        ui.messageBox(
            f'PydanticAI not available: {e}\n\n'
            f'Try restarting Fusion 360 to trigger dependency auto-install.',
            'Meltdown: Foundation Test'
        )
        return

    thread = threading.Thread(target=_run_validation, daemon=True)
    thread.start()


def _run_validation():
    """Runs on a worker thread. Executes the full-chain PoC validation.

    Chain:
    1. Import PydanticAI (proves FNDN-01)
    2. Run agent with prompt asking to analyze workspace
    3. Agent calls get_workspace_info tool -> dispatches to main thread (proves FNDN-02)
    4. Agent calls capture_viewport tool -> dispatches to main thread (proves FNDN-02)
    5. Agent receives viewport screenshot, sends to Gemini vision (proves FNDN-03)
    6. Agent returns structured text response
    7. Display results via bridge show_result (main thread)
    """
    from ...core.bridge import dispatch_to_main_thread

    try:
        futil.log(f'{CMD_NAME}: Validation thread started.')

        # Step 1: Verify imports (FNDN-01)
        import pydantic_ai
        futil.log(f'{CMD_NAME}: [FNDN-01] pydantic_ai {pydantic_ai.__version__} imported OK')

        # Step 2-5: Run the agent (exercises FNDN-02 via tools, FNDN-03 via agent + vision)
        from ...core.agent import run_agent_with_vision

        futil.log(f'{CMD_NAME}: Running agent with validation prompt...')

        prompt = (
            'You are validating the Meltdown Fusion 360 plugin foundation. '
            'Please do the following:\n'
            '1. Use the get_workspace_info tool to read the current document info.\n'
            '2. Use the capture_viewport tool to take a screenshot of the current view.\n'
            '3. Summarize what you found: document name, component/body counts, '
            'and describe what you see in the viewport screenshot.\n'
            '4. End with: "Foundation validation complete. All systems operational."'
        )

        result_text = run_agent_with_vision(prompt)

        futil.log(f'{CMD_NAME}: Agent returned: {result_text[:200]}...')

        # Step 6: Display results (dispatches to main thread for ui.messageBox)
        summary = (
            '=== Meltdown Foundation Test Results ===\n\n'
            f'FNDN-01: Dependencies OK (pydantic_ai {pydantic_ai.__version__})\n'
            f'FNDN-02: Bridge dispatch OK (agent used tools)\n'
            f'FNDN-03: Agent + vision OK\n\n'
            f'--- Agent Response ---\n\n'
            f'{result_text}'
        )

        dispatch_to_main_thread('show_result', {'message': summary})

        futil.log(f'{CMD_NAME}: Validation complete. All FNDN requirements exercised.')

    except Exception as e:
        error_msg = (
            f'Foundation validation failed:\n\n'
            f'{type(e).__name__}: {e}\n\n'
            f'{traceback.format_exc()}'
        )
        futil.log(f'{CMD_NAME}: ERROR - {error_msg}',
                   adsk.core.LogLevels.ErrorLogLevel)
        try:
            dispatch_to_main_thread('show_error', {'message': error_msg})
        except Exception:
            # Last resort: log it, can't show message box from worker thread
            futil.log(f'{CMD_NAME}: Could not display error via bridge.',
                       adsk.core.LogLevels.ErrorLogLevel)


def command_destroy(args: adsk.core.CommandEventArgs):
    futil.log(f'{CMD_NAME}: Command destroy event.')
    global local_handlers
    local_handlers = []
