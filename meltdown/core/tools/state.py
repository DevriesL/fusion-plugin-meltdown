"""State query toolset."""

from pydantic_ai import FunctionToolset

from ..agent_helpers import _check_bridge_result

state_toolset = FunctionToolset()


@state_toolset.tool
def get_design_state() -> dict:
    """Get comprehensive state of the current design: bodies, sketches,
    components, timeline.

    Call this first to understand what exists before making modifications.
    """
    from ..bridge import dispatch_to_main_thread

    result = dispatch_to_main_thread('get_design_state')
    _check_bridge_result(result, 'get_design_state')
    return result


@state_toolset.tool
def get_body_edges(body_name: str) -> dict:
    """List all edges of a body with position coordinates.

    Use before fillet or chamfer to identify which edges to operate on.
    Edges are described by start/end/midpoint coordinates in mm.

    Args:
        body_name: Name of the body (from extrude result or get_design_state).
    """
    from ..bridge import dispatch_to_main_thread

    result = dispatch_to_main_thread('get_body_edges', {
        'body_name': body_name,
    })
    _check_bridge_result(result, 'get_body_edges')
    return result


@state_toolset.tool
def get_body_faces(body_name: str) -> dict:
    """List all faces of a body with centroid position and area.

    Use before shell or hole operations to identify which face to target.

    Args:
        body_name: Name of the body (from extrude result or get_design_state).
    """
    from ..bridge import dispatch_to_main_thread

    result = dispatch_to_main_thread('get_body_faces', {
        'body_name': body_name,
    })
    _check_bridge_result(result, 'get_body_faces')
    return result


@state_toolset.tool
def get_active_selection() -> dict:
    """Read the user's current selection in Fusion 360.

    If the user says 'fillet this edge', call this to see what they
    have selected.
    """
    from ..bridge import dispatch_to_main_thread

    result = dispatch_to_main_thread('get_active_selection')
    _check_bridge_result(result, 'get_active_selection')
    return result
