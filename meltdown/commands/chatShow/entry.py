"""Meltdown: Chat command.

Phase 3 chat interface: opens a palette with a conversational UI for
interacting with the Meltdown AI agent. Users type natural language
prompts, see real-time narration as the agent works, and receive
responses in a bubble-style message stream.

Features:
- Bubble-style chat UI (user blue right, AI gray left)
- Real-time narration streaming during agent operations
- Multi-turn conversation with history persistence
- /clear to reset conversation, /stop to cancel agent work
- Message queueing when agent is busy (D-16)
- Auto-show on startup via workspaceActivated one-shot (D-13)
- History restoration when palette is reopened (D-10)
"""
import json
import os
import threading
import traceback

import adsk.core
from ...lib import fusionAddInUtils as futil
from ... import config

app = adsk.core.Application.get()
ui = app.userInterface

CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_ChatShow'
CMD_NAME = 'Meltdown: Chat'
CMD_Description = 'Open the Meltdown AI chat interface'
IS_PROMOTED = True

WORKSPACE_ID = 'FusionSolidEnvironment'
PANEL_ID = 'SolidScriptsAddinsPanel'
COMMAND_BESIDE_ID = 'ScriptsManagerCommand'

PALETTE_DOCKING = adsk.core.PaletteDockingStates.PaletteDockStateRight

# Palette HTML URL (local file path converted to URL format)
PALETTE_URL = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'resources', 'html', 'index.html'
)
PALETTE_URL = PALETTE_URL.replace('\\', '/')

ICON_FOLDER = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'resources', ''
)

# Local list of event handlers used to maintain a reference so
# they are not released and garbage collected.
local_handlers = []

# Auto-show state (D-13)
_palette_initialized = False
_workspace_handler = None

# Session state (Phase 8)
_current_session_id = None
_current_session_created_at = None


# ******** Lifecycle ********

def start():
    """Register chat command button and auto-show handler."""
    global _workspace_handler

    # Create command definition
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
    )
    futil.add_handler(cmd_def.commandCreated, command_created)

    # Add button to UI
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    control = panel.controls.addCommand(cmd_def, COMMAND_BESIDE_ID, False)
    control.isPromoted = IS_PROMOTED

    # Register slash commands into the central registry (D-11)
    from ...core import command_registry
    command_registry.register(
        'clear',
        'Clear conversation history',
        lambda data, send_fn: _handle_clear(),
    )
    command_registry.register(
        'stop',
        'Stop current operation',
        lambda data, send_fn: _handle_stop(),
    )
    command_registry.register(
        'config',
        'Open settings',
        lambda data, send_fn: _send_to_palette('show_config', '{}'),
    )
    command_registry.register(
        'debug',
        'Toggle debug log panel',
        lambda data, send_fn: _send_to_palette('toggle_debug', '{}'),
    )
    command_registry.register(
        'history',
        'Browse saved sessions',
        lambda data, send_fn: _send_to_palette('show_history', '{}'),
    )
    command_registry.register(
        'resume',
        'Resume a saved session',
        lambda data, send_fn: _send_to_palette('show_history', '{}'),
    )

    # Register one-shot workspaceActivated handler for auto-show (D-13)
    _workspace_handler = futil.add_handler(
        ui.workspaceActivated, _on_workspace_activated
    )

    # Initialize session state from last active session (D-09)
    _init_session_state()


def stop():
    """Clean up command, palette, and workspace handler."""
    global _workspace_handler

    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    command_control = panel.controls.itemById(CMD_ID)
    command_definition = ui.commandDefinitions.itemById(CMD_ID)
    palette = ui.palettes.itemById(config.CHAT_PALETTE_ID)

    if command_control:
        command_control.deleteMe()
    if command_definition:
        command_definition.deleteMe()
    if palette:
        palette.deleteMe()

    # Remove workspace handler if still registered
    if _workspace_handler:
        try:
            ui.workspaceActivated.remove(_workspace_handler)
        except Exception:
            pass
        _workspace_handler = None


# ******** Auto-show on startup (D-13) ********

def _on_workspace_activated(args: adsk.core.WorkspaceEventArgs):
    """One-shot handler: create/show palette on first workspace activation.

    Uses _palette_initialized flag as safety guard to ensure this only
    fires once. After showing the palette, unregisters itself.
    """
    global _palette_initialized, _workspace_handler

    if _palette_initialized:
        return
    _palette_initialized = True

    try:
        _ensure_palette_exists()
    except Exception:
        futil.handle_error('_on_workspace_activated')

    # Remove one-shot handler
    if _workspace_handler:
        try:
            ui.workspaceActivated.remove(_workspace_handler)
        except Exception:
            pass
        _workspace_handler = None


# ******** Session state initialization (Phase 8) ********

def _init_session_state():
    """Load last active session ID from settings, or create a new one."""
    global _current_session_id, _current_session_created_at
    from ...core import settings
    stored_id = settings.get('active_session_id')
    if stored_id:
        from ...core import session_store
        session_data = session_store.load_session(stored_id)
        if session_data:
            _current_session_id = stored_id
            _current_session_created_at = session_data.get('metadata', {}).get('created_at')
            return
    # No valid stored session -- create fresh ID
    from ...core import session_store
    _current_session_id = session_store.create_session_id()
    _current_session_created_at = None


# ******** Command handlers ********

def command_created(args: adsk.core.CommandCreatedEventArgs):
    """Register execute and destroy handlers when command is created."""
    futil.log(f'{CMD_NAME}: Command created event.')
    futil.add_handler(
        args.command.execute, command_execute, local_handlers=local_handlers
    )
    futil.add_handler(
        args.command.destroy, command_destroy, local_handlers=local_handlers
    )


def command_execute(args: adsk.core.CommandEventArgs):
    """Show the chat palette when the toolbar button is clicked."""
    futil.log(f'{CMD_NAME}: Command execute event.')
    _ensure_palette_exists()


def command_destroy(args: adsk.core.CommandEventArgs):
    """Clean up local handlers when command is destroyed."""
    futil.log(f'{CMD_NAME}: Command destroy event.')
    global local_handlers
    local_handlers = []


# ******** Palette lifecycle ********

def _ensure_palette_exists():
    """Create the chat palette if it doesn't exist, then show it."""
    palette = ui.palettes.itemById(config.CHAT_PALETTE_ID)
    if palette is None:
        palette = ui.palettes.add(
            id=config.CHAT_PALETTE_ID,
            name=config.CHAT_PALETTE_NAME,
            htmlFileURL=PALETTE_URL,
            isVisible=True,
            showCloseButton=True,
            isResizable=True,
            width=config.CHAT_PALETTE_WIDTH,
            height=config.CHAT_PALETTE_HEIGHT,
            useNewWebBrowser=True,
        )
        futil.add_handler(palette.closed, palette_closed)
        futil.add_handler(palette.navigatingURL, palette_navigating)
        futil.add_handler(palette.incomingFromHTML, palette_incoming)
        futil.log(f'{CMD_NAME}: Created palette: ID = {palette.id}')

    if palette.dockingState == adsk.core.PaletteDockingStates.PaletteDockStateFloating:
        palette.dockingState = PALETTE_DOCKING

    palette.isVisible = True


def palette_closed(args: adsk.core.UserInterfaceGeneralEventArgs):
    """Log palette closure and clean up debug log relay."""
    from ...core import debug_log
    from ...lib.fusionAddInUtils.general_utils import clear_log_hook
    debug_log.clear_dispatch()
    clear_log_hook()
    futil.log(f'{CMD_NAME}: Palette was closed.')


def palette_navigating(args: adsk.core.NavigationEventArgs):
    """Open external URLs in the user's default browser."""
    url = args.navigationURL
    futil.log(f'{CMD_NAME}: Palette navigating to {url}')
    if url.startswith('http'):
        args.launchExternally = True


def _handle_user_message(data):
    """Handle user_message action from the chat UI JavaScript."""
    from ...core import chat_state

    text = data.get('text', '').strip()
    image = data.get('image')  # base64 data URI from JS (D-11)

    # Registry-based slash command dispatch (D-11, SLSH-04)
    if text.startswith('/'):
        cmd_name = text[1:].split()[0].lower()
        from ...core import command_registry
        if command_registry.execute(cmd_name, data, _send_to_palette):
            return  # Command handled
        # Unknown /command: fall through to agent as normal message (D-04)

    if chat_state.is_agent_busy():
        chat_state.enqueue_message(text)
        futil.log(f'{CMD_NAME}: Message queued (agent busy)')
    else:
        _start_agent_thread(text, image_data=image)


def _handle_palette_ready(data):
    """Handle palette_ready action from the chat UI JavaScript."""
    _restore_history_to_palette()
    # Wire debug log relay to palette
    from ...core import debug_log
    from ...lib.fusionAddInUtils.general_utils import set_log_hook, clear_log_hook

    def _debug_dispatch(payload):
        _send_to_palette(payload['action'], json.dumps(payload))

    debug_log.set_dispatch(_debug_dispatch)
    set_log_hook(debug_log.log_hook)


def _handle_get_design_names(data):
    """Handle get_design_names action from the chat UI JavaScript."""
    # Autocomplete request from JS (D-18)
    # Called directly -- palette_incoming runs on the main thread,
    # so dispatch_to_main_thread would deadlock (INT-01).
    try:
        import adsk.fusion
        design = adsk.fusion.Design.cast(app.activeProduct)
        if design:
            from ...core.state_ops import get_design_names
            result = get_design_names(design)
            _send_to_palette('design_names', json.dumps(result))
    except Exception:
        pass  # Autocomplete failure is non-critical


def _handle_request_file_dialog(data):
    """Handle request_file_dialog action from the chat UI JavaScript."""
    # Fallback image picker via Fusion native dialog (Research Pitfall 4)
    # Called directly -- palette_incoming runs on the main thread,
    # so dispatch_to_main_thread would deadlock (INT-01).
    try:
        dlg = ui.createFileDialog()
        dlg.title = 'Select Reference Image'
        dlg.filter = 'Images (*.png *.jpg *.jpeg *.webp);;All Files (*.*)'
        dlg.isMultiSelectEnabled = False
        if dlg.showOpen() == adsk.core.DialogResults.DialogOK:
            filepath = dlg.filename
            import base64
            with open(filepath, 'rb') as f:
                img_data = base64.b64encode(f.read()).decode('utf-8')
            ext = filepath.rsplit('.', 1)[-1].lower()
            mime = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'webp': 'image/webp'}.get(ext, 'image/png')
            data_uri = f'data:{mime};base64,{img_data}'
            _send_to_palette('file_dialog_result', json.dumps({'image': data_uri}))
    except Exception:
        pass


def _handle_get_commands(data):
    """Handle get_commands action from the chat UI JavaScript."""
    # Slash menu requests available commands (SLSH-01)
    from ...core import command_registry
    commands_list = command_registry.get_menu_commands()
    _send_to_palette('command_list', json.dumps({'commands': commands_list}))


def _handle_load_settings(data):
    """Handle load_settings action from the chat UI JavaScript."""
    # Config overlay requests current settings (CONF-01)
    from ...core import settings
    from ...core.secrets import load_all_keys
    current = settings.load()
    current['api_keys'] = load_all_keys()
    _send_to_palette('settings_data', json.dumps(current))


def _handle_save_settings(data):
    """Handle save_settings action from the chat UI JavaScript."""
    # Config overlay saves new settings (CONF-04)
    from ...core import settings
    from ...core.secrets import save_provider_key

    # Save per-provider API keys (only those that changed)
    api_keys = data.get('api_keys', {})
    for provider, key_value in api_keys.items():
        if key_value and not key_value.startswith('****'):
            save_provider_key(provider, key_value)
            # Set env var immediately for current session
            import os as _os
            env_map = {'gemini': 'GOOGLE_API_KEY', 'claude': 'ANTHROPIC_API_KEY', 'openai': 'OPENAI_API_KEY'}
            env_var = env_map.get(provider)
            if env_var:
                _os.environ[env_var] = key_value

    settings_data = {
        'ai_provider': data.get('ai_provider', 'gemini'),
        'ai_model_name': data.get('ai_model_name', 'gemini-3.1-pro-preview'),
        'max_visual_iterations': int(data.get('max_visual_iterations', 5)),
        'viewport_capture_width': int(data.get('viewport_capture_width', 1920)),
        'viewport_capture_height': int(data.get('viewport_capture_height', 1080)),
        'agent_dispatch_timeout': int(data.get('agent_dispatch_timeout', 60)),
        'debug': bool(data.get('debug', True)),
    }
    settings.save(settings_data)
    _send_to_palette('settings_saved', '{}')


def _handle_load_sessions(data):
    """Handle load_sessions action from the chat UI JavaScript."""
    # History overlay requests session list (SESS-02)
    from ...core import session_store
    sessions = session_store.list_sessions()
    # Mark current session (D-11)
    for s in sessions:
        s['is_current'] = (s['id'] == _current_session_id)
    _send_to_palette('session_list', json.dumps({'sessions': sessions}))


def _handle_resume_session_action(data):
    """Handle resume_session action from the chat UI JavaScript."""
    # User clicked a session card to resume (D-03, SESS-03)
    _handle_resume_session(data.get('session_id', ''))


def _handle_delete_session(data):
    """Handle delete_session action from the chat UI JavaScript."""
    # User deleted a session from history
    from ...core import session_store
    sid = data.get('session_id', '')
    if sid and sid != _current_session_id:
        session_store.delete_session(sid)
        # Refresh the list
        sessions = session_store.list_sessions()
        for s in sessions:
            s['is_current'] = (s['id'] == _current_session_id)
        _send_to_palette('session_list', json.dumps({'sessions': sessions}))


_ACTION_HANDLERS = {
    'user_message': _handle_user_message,
    'palette_ready': _handle_palette_ready,
    'get_design_names': _handle_get_design_names,
    'request_file_dialog': _handle_request_file_dialog,
    'get_commands': _handle_get_commands,
    'load_settings': _handle_load_settings,
    'save_settings': _handle_save_settings,
    'load_sessions': _handle_load_sessions,
    'resume_session': _handle_resume_session_action,
    'delete_session': _handle_delete_session,
}


def palette_incoming(html_args: adsk.core.HTMLEventArgs):
    """Handle messages from the chat UI JavaScript."""
    data = json.loads(html_args.data)
    action = html_args.action

    futil.log(f'{CMD_NAME}: Palette incoming: action={action}')

    handler = _ACTION_HANDLERS.get(action)
    if handler:
        handler(data)

    html_args.returnData = 'OK'


# ******** Chat commands ********

def _handle_clear():
    """Save current session to history, then start fresh (D-08)."""
    global _current_session_id, _current_session_created_at
    from ...core import chat_state, session_store, settings

    # Save current session before clearing (D-08, D-04)
    if _current_session_id and chat_state.get_display_messages():
        try:
            session_store.save_session(
                _current_session_id,
                chat_state.get_display_messages(),
                chat_state.get_history(),
                created_at=_current_session_created_at,
            )
            futil.log(f'{CMD_NAME}: Session {_current_session_id[:8]} saved before clear')
        except Exception as e:
            futil.log(f'{CMD_NAME}: Session save on clear failed: {e}')

    # Start fresh session
    _current_session_id = session_store.create_session_id()
    _current_session_created_at = None
    _save_active_session_id()

    chat_state.clear_history()
    _send_to_palette('clear_chat', '{}')
    futil.log(f'{CMD_NAME}: Conversation cleared, new session {_current_session_id[:8]}')


def _handle_stop():
    """Cancel the current agent operation (D-15)."""
    from ...core import chat_state
    chat_state.request_cancel()
    _send_to_palette('system_message', json.dumps({'text': 'Stopping...'}))
    futil.log(f'{CMD_NAME}: Cancel requested')


def _auto_save_session():
    """Auto-save current session to disk after agent turn (SESS-01, D-10)."""
    from ...core import chat_state, session_store

    if not _current_session_id:
        return

    try:
        display_msgs = chat_state.get_display_messages()
        agent_history = chat_state.get_history()
        if not display_msgs:
            return  # Nothing to save

        session_store.save_session(
            _current_session_id,
            display_msgs,
            agent_history,
            created_at=_current_session_created_at,
        )
        _save_active_session_id()
    except Exception as e:
        futil.log(f'{CMD_NAME}: Auto-save failed: {e}')


def _save_active_session_id():
    """Persist active session ID to settings for restart recovery (D-09)."""
    from ...core import settings
    current_settings = settings.load()
    current_settings['active_session_id'] = _current_session_id
    settings.save(current_settings)


def _handle_resume_session(session_id):
    """Resume a session: save current, load selected, restore UI + agent (D-03, D-04, D-05)."""
    global _current_session_id, _current_session_created_at
    from ...core import chat_state, session_store, settings
    from pydantic_ai.messages import ModelMessagesTypeAdapter

    if not session_id:
        return

    # If resuming the current session, just hide the overlay
    if session_id == _current_session_id:
        _send_to_palette('hide_history', '{}')
        return

    # D-04: Save current session first (no data loss)
    if _current_session_id and chat_state.get_display_messages():
        try:
            session_store.save_session(
                _current_session_id,
                chat_state.get_display_messages(),
                chat_state.get_history(),
                created_at=_current_session_created_at,
            )
        except Exception as e:
            futil.log(f'{CMD_NAME}: Save before resume failed: {e}')

    # Load selected session
    session_data = session_store.load_session(session_id)
    if not session_data:
        _send_to_palette('system_message', json.dumps({'text': 'Session not found.'}))
        _send_to_palette('hide_history', '{}')
        return

    # Update current session tracking
    _current_session_id = session_id
    _current_session_created_at = session_data.get('metadata', {}).get('created_at')
    _save_active_session_id()

    # Clear current state
    chat_state.clear_history()

    # Restore display messages (D-06: text-only)
    display_msgs = session_data.get('display_messages', [])

    # Restore agent history (D-05: full AI context restore)
    agent_history_raw = session_data.get('agent_history')
    ai_context_restored = False
    if agent_history_raw is not None:
        try:
            history_json = json.dumps(agent_history_raw).encode('utf-8')
            restored_messages = ModelMessagesTypeAdapter.validate_json(history_json)
            chat_state.update_history(list(restored_messages))
            ai_context_restored = True
        except Exception as e:
            futil.log(f'{CMD_NAME}: Agent history resume failed: {e}')

    # Restore display messages into chat_state for future saves
    for msg in display_msgs:
        chat_state.add_display_message(msg.get('role', 'user'), msg.get('text', ''))

    # Send to UI: hide overlay, restore messages
    _send_to_palette('hide_history', '{}')
    _send_to_palette('restore_history', json.dumps({'messages': display_msgs}))

    if not ai_context_restored and agent_history_raw is not None:
        # D-07: Graceful degradation
        _send_to_palette('system_message', json.dumps({
            'text': 'Session restored, but AI context could not be recovered. The AI will not remember previous conversation.'
        }))

    futil.log(f'{CMD_NAME}: Resumed session {session_id[:8]} ({len(display_msgs)} messages, AI context: {ai_context_restored})')


# ******** Palette communication helpers ********

def _send_to_palette(action, data_json):
    """Send a message to the chat palette via sendInfoToHTML."""
    palette = ui.palettes.itemById(config.CHAT_PALETTE_ID)
    if palette and palette.isVisible:
        palette.sendInfoToHTML(action, data_json)


def _restore_history_to_palette():
    """Restore session from disk on palette load/reopen (D-09, D-10)."""
    global _current_session_id, _current_session_created_at
    from ...core import chat_state, session_store, settings
    from pydantic_ai.messages import ModelMessagesTypeAdapter

    session_id = _current_session_id
    if not session_id:
        session_id = settings.get('active_session_id')

    if session_id:
        session_data = session_store.load_session(session_id)
        if session_data:
            _current_session_id = session_id
            _current_session_created_at = session_data.get('metadata', {}).get('created_at')

            # Restore display messages to UI (D-06: text-only, no tool cards)
            display_msgs = session_data.get('display_messages', [])
            if display_msgs:
                _send_to_palette('restore_history', json.dumps({'messages': display_msgs}))

            # Restore agent history for AI continuity (D-05)
            agent_history_raw = session_data.get('agent_history')
            if agent_history_raw is not None:
                try:
                    history_json = json.dumps(agent_history_raw).encode('utf-8')
                    restored_messages = ModelMessagesTypeAdapter.validate_json(history_json)
                    chat_state.update_history(list(restored_messages))
                    futil.log(f'{CMD_NAME}: Session {session_id[:8]} restored with AI context')
                except Exception as e:
                    # D-07: Degrade gracefully -- UI restored, AI context lost
                    futil.log(f'{CMD_NAME}: Agent history restore failed: {e}')
                    _send_to_palette('system_message', json.dumps({
                        'text': 'Session restored, but AI context could not be recovered. The AI will not remember previous conversation.'
                    }))
            else:
                futil.log(f'{CMD_NAME}: Session {session_id[:8]} restored (UI only, no agent history)')

            futil.log(f'{CMD_NAME}: Session restored ({len(display_msgs)} messages)')
            return

    # No session to restore -- show whatever is in memory
    messages = chat_state.get_display_messages()
    if messages:
        _send_to_palette('restore_history', json.dumps({'messages': messages}))
    futil.log(f'{CMD_NAME}: History restored ({len(messages)} messages)')


# ******** Agent dispatch ********

def _start_agent_thread(text, image_data=None):
    """Dispatch a user message to the modeling agent on a worker thread.

    Args:
        text: User message text.
        image_data: Optional base64 data URI string (data:image/...;base64,...) per D-11.
    """
    global _current_session_id, _current_session_created_at
    from ...core import chat_state

    if not _current_session_id:
        from ...core import session_store
        _current_session_id = session_store.create_session_id()
    if not _current_session_created_at:
        from datetime import datetime, timezone
        _current_session_created_at = datetime.now(timezone.utc).isoformat()

    chat_state.add_display_message('user', text)
    _send_to_palette('typing_indicator', json.dumps({'show': True}))
    chat_state.set_agent_busy()
    chat_state.reset_cancel()

    thread = threading.Thread(target=_run_agent, args=(text, image_data), daemon=True)
    thread.start()


def _run_agent(text, image_data=None):
    """Worker thread: run the modeling agent and send response to palette."""
    from ...core import chat_state
    from ...core.agent import run_modeling_agent
    from ...core.secrets import ensure_api_key
    from ...core.bridge import dispatch_to_main_thread
    from ...core.debug_log import dispatch_log

    try:
        dispatch_log(f'Agent run started: "{text[:80]}"', level='INFO', source='agent')
        if not ensure_api_key():
            dispatch_to_main_thread('send_to_palette', {
                'action': 'system_message',
                'text': 'No API key configured. Use "Meltdown: Set API Key" command.',
            })
            return

        # Resolve @references (D-01)
        from ...core.context_parser import has_references, resolve_references
        import base64
        import tempfile

        agent_prompt = text
        agent_image_path = None

        if has_references(text):
            ref_result = resolve_references(text)
            if ref_result['context_preamble']:
                agent_prompt = ref_result['context_preamble'] + '\n\n' + text
            if ref_result['image_path']:
                agent_image_path = ref_result['image_path']
            # Show reference errors as system messages (D-20)
            for err in ref_result.get('errors', []):
                dispatch_to_main_thread('send_to_palette', {
                    'action': 'system_message',
                    'text': f'Reference warning: {err}',
                })

        # Handle attached reference image (D-11)
        if image_data and image_data.startswith('data:image/'):
            try:
                # Extract base64 from data URI: "data:image/png;base64,AAAA..."
                header, b64_data = image_data.split(',', 1)
                img_bytes = base64.b64decode(b64_data)
                # Write to temp file for run_modeling_agent
                ext = 'png'
                if 'jpeg' in header or 'jpg' in header:
                    ext = 'jpg'
                elif 'webp' in header:
                    ext = 'webp'
                import uuid as _uuid
                tmp_path = os.path.join(
                    tempfile.gettempdir(),
                    f'meltdown_ref_{_uuid.uuid4().hex[:8]}.{ext}'
                )
                with open(tmp_path, 'wb') as f:
                    f.write(img_bytes)
                # Reference image takes priority if no @view screenshot
                if not agent_image_path:
                    agent_image_path = tmp_path
            except Exception as e:
                futil.log(f'{CMD_NAME}: Image decode error: {e}')

        history = chat_state.get_history()
        response_text, all_messages = run_modeling_agent(
            agent_prompt, image_path=agent_image_path,
            message_history=history if history else None
        )

        if chat_state.is_cancelled():
            dispatch_log('Agent run cancelled', level='WARN', source='agent')
            dispatch_to_main_thread('send_to_palette', {
                'action': 'agent_response',
                'text': 'Operation cancelled.',
            })
            chat_state.add_display_message('assistant', 'Operation cancelled.')
            # Auto-save session (SESS-01, D-10)
            _auto_save_session()
        else:
            dispatch_log('Agent run complete', level='INFO', source='agent')
            chat_state.update_history(all_messages)
            chat_state.add_display_message('assistant', response_text)
            # Auto-save session (SESS-01, D-10)
            _auto_save_session()
            dispatch_to_main_thread('send_to_palette', {
                'action': 'agent_response',
                'text': response_text,
            })

    except Exception as e:
        dispatch_log(f'Agent error: {type(e).__name__}: {e}', level='ERROR', source='agent')
        error_msg = f'Error: {type(e).__name__}: {e}'
        futil.log(f'{CMD_NAME}: {error_msg}', adsk.core.LogLevels.ErrorLogLevel)
        try:
            dispatch_to_main_thread('send_to_palette', {
                'action': 'agent_response',
                'text': error_msg,
            })
            chat_state.add_display_message('assistant', error_msg)
            _auto_save_session()
        except Exception:
            pass

    finally:
        chat_state.clear_agent_busy()
        chat_state.reset_cancel()
        # Process queued messages (D-16)
        next_msg = chat_state.dequeue_message()
        if next_msg:
            _start_agent_thread(next_msg)
