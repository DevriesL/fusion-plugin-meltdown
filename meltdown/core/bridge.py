"""Main-thread dispatch bridge.

Enables worker threads (where PydanticAI agent runs) to execute Fusion API
calls on the main thread and receive results synchronously.

Architecture (per Research Pattern 2):
- Worker thread: calls dispatch_to_main_thread(operation, params)
- Creates a Future, stores it keyed by request UUID
- Fires custom event via app.fireCustomEvent() (only Fusion API call safe from worker threads)
- Blocks on future.result(timeout)
- Main thread: BridgeEventHandler.notify() runs when Fusion processes the event
- Looks up operation, executes it, sets result on the Future
- Worker thread unblocks and receives the result

CRITICAL: All Fusion API calls (except fireCustomEvent) MUST happen in the
handler's notify(), never on a worker thread. Violating this can crash Fusion.

Error handling: When an operation raises an exception, the bridge returns a
structured error dict (error=True, error_type, error_message) instead of
propagating the exception. This enables the agent to receive actionable error
context for self-correction (MODL-06).
"""
import json
import os
import tempfile
import threading
import uuid
from concurrent.futures import Future

import adsk.core
import adsk.fusion

from .. import config

CUSTOM_EVENT_ID = config.BRIDGE_EVENT_ID

# Thread-safe dictionary of pending requests
_pending: dict[str, Future] = {}
_lock = threading.Lock()

# References to prevent garbage collection (Research Pitfall 3)
_custom_event = None
_handler = None


class BridgeEventHandler(adsk.core.CustomEventHandler):
    """Handles dispatched requests on the main thread."""

    def __init__(self):
        super().__init__()

    def notify(self, args: adsk.core.CustomEventArgs):
        """Called on the main thread when a custom event is fired."""
        request_id = None
        try:
            request = json.loads(args.additionalInfo)
            request_id = request['id']
            operation = request['operation']
            params = request.get('params', {})

            result = _execute_operation(operation, params)

            with _lock:
                future = _pending.pop(request_id, None)
            if future:
                future.set_result(result)

        except Exception as e:
            error_result = {
                'error': True,
                'error_type': type(e).__name__,
                'error_message': str(e),
            }
            if request_id:
                with _lock:
                    future = _pending.pop(request_id, None)
                if future:
                    future.set_result(error_result)


def setup_bridge():
    """Register the custom event. Call once during add-in startup (main thread).

    Must be called AFTER ensure_dependencies() succeeds, but BEFORE any
    agent code runs.
    """
    global _custom_event, _handler
    app = adsk.core.Application.get()
    _custom_event = app.registerCustomEvent(CUSTOM_EVENT_ID)
    _handler = BridgeEventHandler()
    _custom_event.add(_handler)


def teardown_bridge():
    """Unregister the custom event. Call during add-in shutdown (main thread)."""
    global _custom_event, _handler
    try:
        app = adsk.core.Application.get()
        if _custom_event and _handler:
            _custom_event.remove(_handler)
        app.unregisterCustomEvent(CUSTOM_EVENT_ID)
    except Exception:
        pass  # Shutting down, best-effort cleanup
    _custom_event = None
    _handler = None


def dispatch_to_main_thread(operation: str, params: dict = None,
                            timeout: float = 30.0) -> dict:
    """Call from a worker thread. Dispatches operation to main thread,
    blocks until result is available.

    Args:
        operation: Name of the Fusion API operation to execute.
                   Supported:
                   Infrastructure: 'get_workspace_info', 'capture_viewport',
                       'show_result', 'show_error', 'show_message_box',
                       'send_to_palette'
                   Modeling: 'create_sketch_rectangle', 'create_sketch_circle',
                       'create_sketch_lines_arcs', 'create_sketch_slot',
                       'create_sketch_polygon',
                       'extrude_profile', 'fillet_edges', 'chamfer_edges',
                       'shell_body', 'create_holes', 'combine_bodies',
                       'rectangular_pattern', 'mirror_body', 'add_thread',
                       'revolve_profile', 'sweep_profile'
                   State: 'get_design_state', 'get_body_edges',
                       'get_body_faces', 'get_active_selection'
                   Transaction: 'get_timeline_position', 'create_timeline_group'
                   Context: 'get_component_details', 'find_named_entity',
                       'set_camera_view', 'get_active_selection_detailed',
                       'get_design_names'
                   Multi-part: 'create_component', 'set_active_component'
                   UI: 'show_image_file_dialog'
        params: Parameters for the operation.
        timeout: Max seconds to wait for result (Research Pitfall 6).

    Returns:
        Dict with operation-specific result data. On error, returns
        {'error': True, 'error_type': str, 'error_message': str}.

    Raises:
        TimeoutError: If main thread doesn't respond within timeout.
    """
    from .chat_state import is_cancelled
    if is_cancelled():
        return {'error': True, 'error_type': 'Cancelled',
                'error_message': 'Operation cancelled by user'}

    request_id = str(uuid.uuid4())
    future = Future()

    with _lock:
        _pending[request_id] = future

    app = adsk.core.Application.get()
    payload = json.dumps({
        'id': request_id,
        'operation': operation,
        'params': params or {}
    })
    app.fireCustomEvent(CUSTOM_EVENT_ID, payload)

    return future.result(timeout=timeout)


def _get_design():
    """Get active Design. Raises ValueError if no design is active."""
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    if design is None:
        raise ValueError('No active Fusion design. Open or create a design first.')
    return design


def _handle_get_workspace_info(app, ui, params):
    design = adsk.fusion.Design.cast(app.activeProduct)
    if design is None:
        return {
            'document_name': app.activeDocument.name if app.activeDocument else 'No document',
            'component_count': 0,
            'body_count': 0,
        }
    return {
        'document_name': app.activeDocument.name,
        'component_count': design.rootComponent.allOccurrences.count + 1,
        'body_count': design.rootComponent.bRepBodies.count,
    }


def _handle_capture_viewport(app, ui, params):
    filepath = params.get('filepath') or os.path.join(
        tempfile.gettempdir(),
        f'meltdown_viewport_{uuid.uuid4().hex[:8]}.png'
    )
    width = params.get('width', 1024)
    height = params.get('height', 768)
    success = app.activeViewport.saveAsImageFile(filepath, width, height)
    return {'success': success, 'filepath': filepath}


def _handle_show_result(app, ui, params):
    message = params.get('message', '')
    ui.messageBox(message, 'Meltdown: Foundation Test')
    return {'shown': True}


def _handle_show_error(app, ui, params):
    message = params.get('message', 'Unknown error')
    ui.messageBox(message, 'Meltdown: Error')
    return {'shown': True}


def _handle_show_message_box(app, ui, params):
    title = params.get('title', 'Meltdown')
    message = params.get('message', '')
    # Returns: 0 = OK, 1 = Cancel (from adsk.core.DialogResults)
    result = ui.messageBox(message, title, adsk.core.MessageBoxButtonTypes.OKCancelButtonType)
    return {'result': 'ok' if result == 0 else 'cancel'}


def _handle_send_to_palette(app, ui, params):
    palette = ui.palettes.itemById(config.CHAT_PALETTE_ID)
    if palette and palette.isVisible:
        action = params.get('action', 'narration')
        data = json.dumps(params)
        palette.sendInfoToHTML(action, data)
    return {'sent': True}


def _handle_create_sketch_rectangle(app, ui, params):
    from .modeling_ops import create_sketch_rectangle
    design = _get_design()
    return create_sketch_rectangle(
        design, params['plane'], params['x1'], params['y1'],
        params['x2'], params['y2'], params.get('sketch_name'),
    )


def _handle_create_sketch_circle(app, ui, params):
    from .modeling_ops import create_sketch_circle
    design = _get_design()
    return create_sketch_circle(
        design, params['plane'], params['center_x'], params['center_y'],
        params['radius'], params.get('sketch_name'),
    )


def _handle_create_sketch_lines_arcs(app, ui, params):
    from .modeling_ops import create_sketch_lines_arcs
    design = _get_design()
    return create_sketch_lines_arcs(
        design, params['plane'], params['start_x'], params['start_y'],
        params['segments'], params.get('sketch_name'),
        params.get('close', True),
    )


def _handle_create_sketch_slot(app, ui, params):
    from .modeling_ops import create_sketch_slot
    design = _get_design()
    return create_sketch_slot(
        design, params['plane'], params['center_x'], params['center_y'],
        params['length'], params['width'], params.get('angle_rad', 0),
        params.get('sketch_name'),
    )


def _handle_create_sketch_polygon(app, ui, params):
    from .modeling_ops import create_sketch_polygon
    design = _get_design()
    return create_sketch_polygon(
        design, params['plane'], params['center_x'], params['center_y'],
        params['inscribed_radius'], params['side_count'],
        params.get('angle_rad', 0), params.get('sketch_name'),
    )


def _handle_extrude_profile(app, ui, params):
    from .modeling_ops import extrude_profile
    design = _get_design()
    return extrude_profile(
        design, params['sketch_name'], params['profile_index'],
        params['distance_cm'], params.get('operation', 'new'),
    )


def _handle_fillet_edges(app, ui, params):
    from .modeling_ops import fillet_edges
    design = _get_design()
    return fillet_edges(
        design, params['body_name'], params['edge_indices'],
        params['radius_cm'],
    )


def _handle_chamfer_edges(app, ui, params):
    from .modeling_ops import chamfer_edges
    design = _get_design()
    return chamfer_edges(
        design, params['body_name'], params['edge_indices'],
        params['distance_cm'],
    )


def _handle_shell_body(app, ui, params):
    from .modeling_ops import shell_body
    design = _get_design()
    return shell_body(
        design, params['body_name'], params['face_indices_to_remove'],
        params['thickness_cm'],
    )


def _handle_create_holes(app, ui, params):
    from .modeling_ops import create_holes
    design = _get_design()
    return create_holes(
        design, params['face_index'], params['body_name'],
        params['points_cm'], params['diameter_cm'], params['depth_cm'],
    )


def _handle_combine_bodies(app, ui, params):
    from .modeling_ops import combine_bodies
    design = _get_design()
    return combine_bodies(
        design, params['target_body_name'], params['tool_body_names'],
        params.get('operation', 'join'), params.get('keep_tools', False),
    )


def _handle_rectangular_pattern(app, ui, params):
    from .modeling_ops import rectangular_pattern
    design = _get_design()
    return rectangular_pattern(
        design, params['body_name'], params['x_count'],
        params['x_spacing_cm'], params.get('y_count', 1),
        params.get('y_spacing_cm', 0), params.get('direction_one', 'x'),
        params.get('direction_two', 'y'),
    )


def _handle_mirror_body(app, ui, params):
    from .modeling_ops import mirror_body
    design = _get_design()
    return mirror_body(design, params['body_name'], params['plane_name'],
                       params.get('operation', 'new'))


def _handle_add_thread(app, ui, params):
    from .modeling_ops import add_thread
    design = _get_design()
    return add_thread(design, params['body_name'], params['face_index'],
                      params['thread_size'], params.get('is_internal', True),
                      params.get('full_length', True))


def _handle_revolve_profile(app, ui, params):
    from .modeling_ops import revolve_profile
    design = _get_design()
    return revolve_profile(design, params['sketch_name'],
                           params['profile_index'], params['axis'],
                           params['angle_rad'],
                           params.get('operation', 'new'))


def _handle_sweep_profile(app, ui, params):
    from .modeling_ops import sweep_profile
    design = _get_design()
    return sweep_profile(design, params['profile_sketch_name'],
                         params['path_sketch_name'],
                         params.get('operation', 'cut'))


def _handle_get_design_state(app, ui, params):
    from .state_ops import get_design_state
    design = _get_design()
    return get_design_state(design)


def _handle_get_body_edges(app, ui, params):
    from .state_ops import get_body_edges
    design = _get_design()
    return get_body_edges(design, params['body_name'])


def _handle_get_body_faces(app, ui, params):
    from .state_ops import get_body_faces
    design = _get_design()
    return get_body_faces(design, params['body_name'])


def _handle_get_active_selection(app, ui, params):
    from .state_ops import get_active_selection
    return get_active_selection(app)


def _handle_get_timeline_position(app, ui, params):
    from .transaction import get_timeline_position
    design = _get_design()
    return {'position': get_timeline_position(design)}


def _handle_create_timeline_group(app, ui, params):
    from .transaction import create_timeline_group
    design = _get_design()
    return create_timeline_group(
        design, params['start_index'], params.get('name', 'AI Operation'),
    )


def _handle_get_component_details(app, ui, params):
    from .state_ops import get_component_details
    design = _get_design()
    return get_component_details(design, params['name'])


def _handle_create_component(app, ui, params):
    from .state_ops import create_component
    design = _get_design()
    return create_component(design, params['name'])


def _handle_set_active_component(app, ui, params):
    from .state_ops import set_active_component
    design = _get_design()
    return set_active_component(design, params['name'])


def _handle_find_named_entity(app, ui, params):
    from .state_ops import find_named_entity
    design = _get_design()
    return find_named_entity(design, params['name'])


def _handle_set_camera_view(app, ui, params):
    from .state_ops import set_camera_view
    return set_camera_view(app, params['view_name'])


def _handle_capture_multi_angle(app, ui, params):
    from .state_ops import capture_multi_angle
    return capture_multi_angle(app, params)


def _handle_get_active_selection_detailed(app, ui, params):
    from .state_ops import get_active_selection_detailed
    return get_active_selection_detailed(app)


def _handle_get_design_names(app, ui, params):
    from .state_ops import get_design_names
    design = _get_design()
    return get_design_names(design)


def _handle_show_image_file_dialog(app, ui, params):
    dlg = ui.createFileDialog()
    dlg.title = 'Select Reference Image'
    dlg.filter = 'Images (*.png *.jpg *.jpeg *.webp);;All Files (*.*)'
    dlg.isMultiSelectEnabled = False
    if dlg.showOpen() == adsk.core.DialogResults.DialogOK:
        return {'filepath': dlg.filename}
    return {'filepath': None, 'cancelled': True}


_DISPATCH_TABLE = {
    # ******** Infrastructure operations ********
    'get_workspace_info': _handle_get_workspace_info,
    'capture_viewport': _handle_capture_viewport,
    'show_result': _handle_show_result,
    'show_error': _handle_show_error,
    'show_message_box': _handle_show_message_box,
    'send_to_palette': _handle_send_to_palette,

    # ******** Modeling operations ********
    'create_sketch_rectangle': _handle_create_sketch_rectangle,
    'create_sketch_circle': _handle_create_sketch_circle,
    'create_sketch_lines_arcs': _handle_create_sketch_lines_arcs,
    'create_sketch_slot': _handle_create_sketch_slot,
    'create_sketch_polygon': _handle_create_sketch_polygon,
    'extrude_profile': _handle_extrude_profile,
    'fillet_edges': _handle_fillet_edges,
    'chamfer_edges': _handle_chamfer_edges,
    'shell_body': _handle_shell_body,
    'create_holes': _handle_create_holes,
    'combine_bodies': _handle_combine_bodies,
    'rectangular_pattern': _handle_rectangular_pattern,
    'mirror_body': _handle_mirror_body,
    'add_thread': _handle_add_thread,
    'revolve_profile': _handle_revolve_profile,
    'sweep_profile': _handle_sweep_profile,

    # ******** State operations ********
    'get_design_state': _handle_get_design_state,
    'get_body_edges': _handle_get_body_edges,
    'get_body_faces': _handle_get_body_faces,
    'get_active_selection': _handle_get_active_selection,

    # ******** Transaction operations ********
    'get_timeline_position': _handle_get_timeline_position,
    'create_timeline_group': _handle_create_timeline_group,

    # ******** Phase 4: Context and multi-part operations ********
    'get_component_details': _handle_get_component_details,
    'create_component': _handle_create_component,
    'set_active_component': _handle_set_active_component,
    'find_named_entity': _handle_find_named_entity,
    'set_camera_view': _handle_set_camera_view,
    'capture_multi_angle': _handle_capture_multi_angle,
    'get_active_selection_detailed': _handle_get_active_selection_detailed,
    'get_design_names': _handle_get_design_names,

    'show_image_file_dialog': _handle_show_image_file_dialog,
}


def _execute_operation(operation: str, params: dict) -> dict:
    """Execute a Fusion API operation on the main thread.

    This runs inside BridgeEventHandler.notify() -- guaranteed main thread.
    Routes 35 operations: 5 infrastructure, 16 modeling, 4 state, 2 transaction,
    8 context/multi-part.
    """
    app = adsk.core.Application.get()
    ui = app.userInterface

    handler = _DISPATCH_TABLE.get(operation)
    if handler is None:
        raise ValueError(f'Unknown bridge operation: {operation}')
    return handler(app, ui, params)
