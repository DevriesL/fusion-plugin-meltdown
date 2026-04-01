"""Compound higher-level modeling tools."""

from pydantic_ai import FunctionToolset

from ..agent_helpers import _check_bridge_result

compound_toolset = FunctionToolset()


@compound_toolset.tool
def create_enclosure(
    width_mm: float,
    depth_mm: float,
    height_mm: float,
    wall_thickness_mm: float,
    fillet_radius_mm: float = 0,
    plane: str = 'xy',
) -> str:
    """Create a CNC-machinable open-top enclosure (box with shell).

    This is a compound operation that creates a rectangle, extrudes it,
    and shells it in one step. Optionally adds fillet to top edges.
    Use this when the user asks for a box, enclosure, case, or housing.

    Args:
        width_mm: Enclosure width in mm.
        depth_mm: Enclosure depth in mm.
        height_mm: Enclosure height in mm.
        wall_thickness_mm: Wall thickness in mm.
        fillet_radius_mm: Optional fillet radius for top edges (0 = no fillet).
        plane: Construction plane (default 'xy').
    """
    from ..bridge import dispatch_to_main_thread

    # Step 1: Create sketch rectangle
    x1 = -width_mm / 2 / 10
    y1 = -depth_mm / 2 / 10
    x2 = width_mm / 2 / 10
    y2 = depth_mm / 2 / 10

    sketch_result = dispatch_to_main_thread('create_sketch_rectangle', {
        'plane': plane,
        'x1': x1, 'y1': y1,
        'x2': x2, 'y2': y2,
    })
    _check_bridge_result(sketch_result, 'create_enclosure/sketch')

    # Step 2: Extrude to height
    extrude_result = dispatch_to_main_thread('extrude_profile', {
        'sketch_name': sketch_result['sketch_name'],
        'profile_index': 0,
        'distance_cm': height_mm / 10,
        'operation': 'new',
    })
    _check_bridge_result(extrude_result, 'create_enclosure/extrude')

    body_name = extrude_result['body_name']

    # Step 3: Find top face (highest Z centroid)
    faces_result = dispatch_to_main_thread('get_body_faces', {
        'body_name': body_name,
    })
    _check_bridge_result(faces_result, 'create_enclosure/get_faces')

    top_face_idx = max(
        faces_result['faces'],
        key=lambda f: f['centroid_mm'][2],
    )['index']

    # Step 4: Shell the body removing the top face
    shell_result = dispatch_to_main_thread('shell_body', {
        'body_name': body_name,
        'face_indices_to_remove': [top_face_idx],
        'thickness_cm': wall_thickness_mm / 10,
    })
    _check_bridge_result(shell_result, 'create_enclosure/shell')

    # Step 5 (optional): Fillet top edges
    fillet_info = ''
    if fillet_radius_mm > 0:
        edges_result = dispatch_to_main_thread('get_body_edges', {
            'body_name': body_name,
        })
        _check_bridge_result(edges_result, 'create_enclosure/get_edges')

        # Find top edges: edges whose midpoint Z is at the max height
        max_z = max(
            e['midpoint'][2] for e in edges_result['edges']
        )
        top_edge_indices = [
            e['index'] for e in edges_result['edges']
            if abs(e['midpoint'][2] - max_z) < 0.1
        ]

        if top_edge_indices:
            fillet_result = dispatch_to_main_thread('fillet_edges', {
                'body_name': body_name,
                'edge_indices': top_edge_indices,
                'radius_cm': fillet_radius_mm / 10,
            })
            _check_bridge_result(fillet_result, 'create_enclosure/fillet')
            fillet_info = f', {fillet_radius_mm}mm fillet'

    return (
        f"Created enclosure {width_mm}x{depth_mm}x{height_mm}mm, "
        f"{wall_thickness_mm}mm walls{fillet_info}"
    )


@compound_toolset.tool
def create_mounting_plate(
    width_mm: float,
    depth_mm: float,
    thickness_mm: float,
    hole_diameter_mm: float,
    hole_inset_mm: float,
    plane: str = 'xy',
) -> str:
    """Create a rectangular mounting plate with bolt holes at each corner.

    Use this when the user asks for a base plate, mounting bracket, or
    panel with corner holes.

    Args:
        width_mm: Plate width in mm.
        depth_mm: Plate depth in mm.
        thickness_mm: Plate thickness in mm.
        hole_diameter_mm: Bolt hole diameter in mm.
        hole_inset_mm: Distance from edges to hole centers in mm.
        plane: Construction plane (default 'xy').
    """
    from ..bridge import dispatch_to_main_thread

    # Step 1: Create sketch rectangle
    x1 = -width_mm / 2 / 10
    y1 = -depth_mm / 2 / 10
    x2 = width_mm / 2 / 10
    y2 = depth_mm / 2 / 10

    sketch_result = dispatch_to_main_thread('create_sketch_rectangle', {
        'plane': plane,
        'x1': x1, 'y1': y1,
        'x2': x2, 'y2': y2,
    })
    _check_bridge_result(sketch_result, 'create_mounting_plate/sketch')

    # Step 2: Extrude to thickness
    extrude_result = dispatch_to_main_thread('extrude_profile', {
        'sketch_name': sketch_result['sketch_name'],
        'profile_index': 0,
        'distance_cm': thickness_mm / 10,
        'operation': 'new',
    })
    _check_bridge_result(extrude_result, 'create_mounting_plate/extrude')

    body_name = extrude_result['body_name']

    # Step 3: Find top face for hole placement
    faces_result = dispatch_to_main_thread('get_body_faces', {
        'body_name': body_name,
    })
    _check_bridge_result(faces_result, 'create_mounting_plate/get_faces')

    top_face_idx = max(
        faces_result['faces'],
        key=lambda f: f['centroid_mm'][2],
    )['index']

    # Step 4: Compute four corner hole positions
    # Rectangle is centered, so corners are at +/- half-width/depth
    half_w = width_mm / 2
    half_d = depth_mm / 2
    hole_points_mm = [
        [-half_w + hole_inset_mm, -half_d + hole_inset_mm],
        [half_w - hole_inset_mm, -half_d + hole_inset_mm],
        [-half_w + hole_inset_mm, half_d - hole_inset_mm],
        [half_w - hole_inset_mm, half_d - hole_inset_mm],
    ]
    # Convert to cm for bridge
    hole_points_cm = [[p[0] / 10, p[1] / 10] for p in hole_points_mm]

    holes_result = dispatch_to_main_thread('create_holes', {
        'body_name': body_name,
        'face_index': top_face_idx,
        'points_cm': hole_points_cm,
        'diameter_cm': hole_diameter_mm / 10,
        'depth_cm': thickness_mm / 10,
    })
    _check_bridge_result(holes_result, 'create_mounting_plate/holes')

    return (
        f"Created mounting plate {width_mm}x{depth_mm}x{thickness_mm}mm "
        f"with 4x {hole_diameter_mm}mm holes at {hole_inset_mm}mm inset"
    )
