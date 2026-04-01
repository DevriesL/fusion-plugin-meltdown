"""Geometry modification toolset."""

from pydantic_ai import FunctionToolset

from ..agent_helpers import _check_bridge_result

modify_toolset = FunctionToolset()


@modify_toolset.tool
def fillet(
    body_name: str,
    edge_indices: list[int],
    radius_mm: float,
) -> str:
    """Apply rounded fillet to edges.

    Use get_body_edges first to identify edge indices by position.

    Args:
        body_name: Name of the body (from extrude result or get_design_state).
        edge_indices: List of edge indices to fillet.
        radius_mm: Fillet radius in millimeters.
    """
    from ..bridge import dispatch_to_main_thread

    result = dispatch_to_main_thread('fillet_edges', {
        'body_name': body_name,
        'edge_indices': edge_indices,
        'radius_cm': radius_mm / 10,
    })
    _check_bridge_result(result, 'fillet')
    return (
        f"Filleted {len(edge_indices)} edges with {radius_mm}mm radius "
        f"-> '{result['feature_name']}' on '{result['body_name']}' "
        f"({result['face_count']} faces, {result['edge_count']} edges)"
    )


@modify_toolset.tool
def chamfer(
    body_name: str,
    edge_indices: list[int],
    distance_mm: float,
) -> str:
    """Apply chamfer (angled cut) to edges.

    Use get_body_edges first to identify edge indices.

    Args:
        body_name: Name of the body (from extrude result or get_design_state).
        edge_indices: List of edge indices to chamfer.
        distance_mm: Chamfer distance in millimeters.
    """
    from ..bridge import dispatch_to_main_thread

    result = dispatch_to_main_thread('chamfer_edges', {
        'body_name': body_name,
        'edge_indices': edge_indices,
        'distance_cm': distance_mm / 10,
    })
    _check_bridge_result(result, 'chamfer')
    return (
        f"Chamfered {len(edge_indices)} edges with {distance_mm}mm distance "
        f"-> '{result['feature_name']}' on '{result['body_name']}' "
        f"({result['face_count']} faces, {result['edge_count']} edges)"
    )


@modify_toolset.tool
def shell(
    body_name: str,
    face_indices_to_remove: list[int],
    thickness_mm: float,
) -> str:
    """Hollow out a body, removing specified faces to create openings.

    Essential for creating enclosures. Use get_body_faces first to identify
    which face to remove (typically the top face for an open-top enclosure).

    Args:
        body_name: Name of the body (from extrude result or get_design_state).
        face_indices_to_remove: Face indices to remove (become openings).
        thickness_mm: Wall thickness in millimeters.
    """
    from ..bridge import dispatch_to_main_thread

    result = dispatch_to_main_thread('shell_body', {
        'body_name': body_name,
        'face_indices_to_remove': face_indices_to_remove,
        'thickness_cm': thickness_mm / 10,
    })
    _check_bridge_result(result, 'shell')
    return (
        f"Shelled body '{body_name}' with {thickness_mm}mm walls, "
        f"removed {len(face_indices_to_remove)} faces "
        f"-> '{result['feature_name']}' "
        f"({result['face_count']} faces, {result['edge_count']} edges)"
    )


@modify_toolset.tool
def create_holes(
    body_name: str,
    face_index: int,
    points_mm: list[list[float]],
    diameter_mm: float,
    depth_mm: float,
) -> str:
    """Create holes at specified points on a face.

    Use get_body_faces to find the face index. Points are [x, y] in mm.

    Args:
        body_name: Name of the body (from extrude result or get_design_state).
        face_index: Zero-based index of the face on the body.
        points_mm: List of [x, y] coordinate pairs in mm.
        diameter_mm: Hole diameter in millimeters.
        depth_mm: Hole depth in millimeters.
    """
    from ..bridge import dispatch_to_main_thread

    # Convert points from mm to cm
    points_cm = [[p[0] / 10, p[1] / 10] for p in points_mm]

    result = dispatch_to_main_thread('create_holes', {
        'body_name': body_name,
        'face_index': face_index,
        'points_cm': points_cm,
        'diameter_cm': diameter_mm / 10,
        'depth_cm': depth_mm / 10,
    })
    _check_bridge_result(result, 'create_holes')
    return (
        f"Created {result['hole_count']} holes "
        f"({diameter_mm}mm dia, {depth_mm}mm deep) "
        f"-> '{result['feature_name']}'"
    )


@modify_toolset.tool
def boolean_combine(
    target_body_name: str,
    tool_body_names: list[str],
    operation: str = 'join',
    keep_tools: bool = False,
) -> str:
    """Boolean combine bodies: 'join' (union), 'cut' (subtract tools
    from target), 'intersect'.

    Args:
        target_body_name: Name of the target body.
        tool_body_names: Names of tool bodies to combine with.
        operation: Boolean operation -- 'join', 'cut', 'intersect'.
        keep_tools: If True, preserve tool bodies after combining.
    """
    from ..bridge import dispatch_to_main_thread

    result = dispatch_to_main_thread('combine_bodies', {
        'target_body_name': target_body_name,
        'tool_body_names': tool_body_names,
        'operation': operation,
        'keep_tools': keep_tools,
    })
    _check_bridge_result(result, 'boolean_combine')
    return (
        f"Combined bodies ({operation}) "
        f"-> '{result['feature_name']}' on '{result['body_name']}' "
        f"({result['face_count']} faces, {result['edge_count']} edges)"
    )


@modify_toolset.tool
def rectangular_pattern(
    body_name: str,
    x_count: int,
    x_spacing_mm: float,
    y_count: int = 1,
    y_spacing_mm: float = 0,
) -> str:
    """Create a rectangular pattern of a body.

    Use for mounting holes, repeated features.

    Args:
        body_name: Name of the body to pattern (from extrude result or get_design_state).
        x_count: Number of instances along X (including original).
        x_spacing_mm: Spacing between instances in mm along X.
        y_count: Instances along Y (default 1, no Y pattern).
        y_spacing_mm: Spacing in mm along Y (default 0).
    """
    from ..bridge import dispatch_to_main_thread

    result = dispatch_to_main_thread('rectangular_pattern', {
        'body_name': body_name,
        'x_count': x_count,
        'x_spacing_cm': x_spacing_mm / 10,
        'y_count': y_count,
        'y_spacing_cm': y_spacing_mm / 10,
    })
    _check_bridge_result(result, 'rectangular_pattern')
    return (
        f"Created {x_count}x{y_count} rectangular pattern "
        f"-> '{result['feature_name']}'"
    )
