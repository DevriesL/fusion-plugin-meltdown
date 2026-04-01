"""Multi-part component management toolset."""

from pydantic_ai import FunctionToolset

from ..agent_helpers import _check_bridge_result

component_toolset = FunctionToolset()


@component_toolset.tool
def create_component(
    name: str,
) -> str:
    """Create a new component (part) in the current design.

    Use this when the user wants to add a separate part to the design, such as
    a bracket, mounting plate, or side panel. Each component has its own bodies,
    sketches, and timeline. After creating, use set_active_component to switch
    to it before adding geometry.

    Args:
        name: Name for the new component (e.g., 'side_panel', 'bracket').
    """
    from ..bridge import dispatch_to_main_thread

    result = dispatch_to_main_thread('create_component', {'name': name})
    _check_bridge_result(result, 'create_component')

    # Narrate the component creation (D-14)
    dispatch_to_main_thread('send_to_palette', {
        'action': 'narration',
        'text': f"Created new component '{result['component_name']}'",
    })

    return f"Created component '{result['component_name']}' (occurrence index {result['occurrence_index']})"


@component_toolset.tool
def set_active_component(
    name: str,
) -> str:
    """Switch the active component for subsequent modeling operations.

    All modeling tools (extrude, fillet, etc.) operate on the active component.
    Use this before adding geometry to a specific part. Use get_design_state
    to see all available components.

    Args:
        name: Name of the component to activate. Use the root component name
              to return to the top level.
    """
    from ..bridge import dispatch_to_main_thread

    result = dispatch_to_main_thread('set_active_component', {'name': name})
    _check_bridge_result(result, 'set_active_component')

    # Narrate the switch (D-14)
    dispatch_to_main_thread('send_to_palette', {
        'action': 'narration',
        'text': f"Switching to component '{result['component_name']}'...",
    })

    return f"Activated component '{result['component_name']}'"


@component_toolset.tool
def get_component_details(
    name: str,
) -> dict:
    """Get detailed state for a specific component: bodies, sketches, bounding box.

    Use this to inspect any component's geometry, even while working on a
    different component. Essential for cross-part referencing (e.g., reading
    a panel's bolt pattern to create matching holes on a bracket).

    Args:
        name: Name of the component to inspect.
    """
    from ..bridge import dispatch_to_main_thread

    result = dispatch_to_main_thread('get_component_details', {'name': name})
    _check_bridge_result(result, 'get_component_details')
    return result
