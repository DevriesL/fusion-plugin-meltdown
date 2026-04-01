"""Feature creation toolset for 3D operations."""

from pydantic_ai import FunctionToolset

from ..agent_helpers import _check_bridge_result

feature_toolset = FunctionToolset()


@feature_toolset.tool(retries=3)
def extrude(
    sketch_name: str,
    profile_index: int,
    distance_mm: float,
    operation: str = 'new',
) -> str:
    """Extrude a sketch profile to create or modify a 3D body.

    Operations: 'new' (create new body), 'join' (add to existing),
    'cut' (subtract), 'intersect'.

    For cut/join/intersect, the direction is auto-detected: if the
    initial direction misses the target body, the opposite direction
    is tried automatically.

    Args:
        sketch_name: Name of the sketch containing the profile.
        profile_index: Zero-based index of the profile to extrude.
        distance_mm: Extrusion distance in mm (sign is auto-corrected
            for cut/join/intersect operations).
        operation: Feature operation -- 'new', 'join', 'cut', 'intersect'.
    """
    from ..bridge import dispatch_to_main_thread

    result = dispatch_to_main_thread('extrude_profile', {
        'sketch_name': sketch_name,
        'profile_index': profile_index,
        'distance_cm': distance_mm / 10,
        'operation': operation,
    })
    _check_bridge_result(result, 'extrude')
    return (
        f"Extruded '{sketch_name}' profile {profile_index} by {distance_mm}mm "
        f"-> body '{result['body_name']}' "
        f"({result['face_count']} faces, {result['edge_count']} edges)"
    )


@feature_toolset.tool
def mirror(
    body_name: str,
    plane: str,
    operation: str = 'new',
) -> str:
    """Mirror a body across a construction plane to create a symmetric copy.

    Use this for symmetric CNC parts -- mirror one half across a plane to
    create the full part. Use operation='join' to merge the mirrored copy
    with the original into a single body (recommended for symmetric
    single-body parts; only works when the body touches the mirror plane).
    Use operation='new' to keep the mirrored copy as a separate body.

    Args:
        body_name: Name of the body to mirror (from extrude result or get_design_state).
        plane: Mirror plane -- 'xy', 'xz', or 'yz'.
        operation: 'new' (separate mirrored copy) or 'join' (merge with original).
    """
    from ..bridge import dispatch_to_main_thread

    result = dispatch_to_main_thread('mirror_body', {
        'body_name': body_name,
        'plane_name': plane,
        'operation': operation,
    })
    _check_bridge_result(result, 'mirror')
    return (
        f"Mirrored '{body_name}' across {plane} plane ({operation}) "
        f"-> '{result['body_name']}' "
        f"({result['face_count']} faces, {result['edge_count']} edges)"
    )


@feature_toolset.tool
def add_thread(
    body_name: str,
    face_index: int,
    thread_size: str,
    is_internal: bool = True,
    full_length: bool = True,
) -> str:
    """Add a standard metric thread to a cylindrical face.

    Use this for fastener holes (internal threads, e.g., M5 for bolts) or
    threaded bosses (external threads). The face MUST be cylindrical -- use
    get_body_faces first to identify cylindrical faces by their surface type.
    Supported sizes: M3, M4, M5, M6, M7, M8.

    Args:
        body_name: Name of the body (from extrude result or get_design_state).
        face_index: Index of the cylindrical face to thread. Use get_body_faces
            to find cylindrical faces.
        thread_size: Metric thread size, e.g. 'M5'. Range: M3 to M8.
        is_internal: True for internal threads (holes), False for external
            threads (bosses). Default True.
        full_length: True to thread the full face length. Default True.
    """
    from ..bridge import dispatch_to_main_thread

    result = dispatch_to_main_thread('add_thread', {
        'body_name': body_name,
        'face_index': face_index,
        'thread_size': thread_size,
        'is_internal': is_internal,
        'full_length': full_length,
    })
    _check_bridge_result(result, 'add_thread')
    thread_type = 'internal' if result['is_internal'] else 'external'
    return (
        f"Added {result['thread_size']} {thread_type} thread ({result['designation']}) "
        f"to face {face_index} on '{result['body_name']}' "
        f"-> '{result['feature_name']}' "
        f"({result['face_count']} faces, {result['edge_count']} edges)"
    )


@feature_toolset.tool(retries=3)
def revolve(
    sketch_name: str,
    profile_index: int,
    axis: str,
    angle_deg: float = 360,
    operation: str = 'new',
) -> str:
    """Revolve a sketch profile around a construction axis to create rotational geometry.

    Use this for cylindrical parts like standoffs, bushings, knobs, or any
    geometry with rotational symmetry. The sketch profile must be entirely on
    one side of the axis (not crossing it). Use angle_deg=360 for a full
    revolution, or partial angles for arc-shaped solids (e.g., 180 for a
    half-pipe, 90 for a quarter-round bracket).

    Args:
        sketch_name: Name of the sketch containing the profile to revolve.
        profile_index: Zero-based index of the sketch profile.
        axis: Revolution axis -- 'x', 'y', or 'z' (construction axis).
        angle_deg: Revolution angle in degrees (1 to 360, default 360).
        operation: Feature operation -- 'new', 'join', 'cut', 'intersect'.
    """
    from ..bridge import dispatch_to_main_thread
    import math

    result = dispatch_to_main_thread('revolve_profile', {
        'sketch_name': sketch_name,
        'profile_index': profile_index,
        'axis': axis,
        'angle_rad': math.radians(angle_deg),
        'operation': operation,
    })
    _check_bridge_result(result, 'revolve')
    angle_str = f"{angle_deg}deg " if angle_deg < 360 else ""
    return (
        f"Revolved '{sketch_name}' profile {profile_index} around {axis}-axis "
        f"{angle_str}({operation}) "
        f"-> body '{result['body_name']}' "
        f"({result['face_count']} faces, {result['edge_count']} edges)"
    )


@feature_toolset.tool
def sweep(
    profile_sketch_name: str,
    path_sketch_name: str,
    operation: str = 'cut',
) -> str:
    """Sweep a profile along a path to create channel/groove geometry.

    Use this for cable channels, gasket grooves, T-slots, and dovetails.
    WORKFLOW: (1) create profile sketch (closed shape on perpendicular plane),
    (2) create path sketch with close=False (open path for sweep direction),
    (3) call sweep.

    The profile plane MUST be perpendicular to the path at its start point.
    Example: path on XY plane requires profile on XZ or YZ plane.

    Args:
        profile_sketch_name: Sketch with the closed profile to sweep.
        path_sketch_name: Sketch with the open path (created with close=False).
        operation: Feature operation -- 'new', 'join', 'cut' (default), 'intersect'.
    """
    from ..bridge import dispatch_to_main_thread

    result = dispatch_to_main_thread('sweep_profile', {
        'profile_sketch_name': profile_sketch_name,
        'path_sketch_name': path_sketch_name,
        'operation': operation,
    })
    _check_bridge_result(result, 'sweep')
    return (
        f"Swept '{profile_sketch_name}' along '{path_sketch_name}' ({operation}) "
        f"-> body '{result['body_name']}' "
        f"({result['face_count']} faces, {result['edge_count']} edges)"
    )
