"""Sketch toolset for primitive 2D profile creation."""

from pydantic_ai import FunctionToolset

from ..agent_helpers import _check_bridge_result

sketch_toolset = FunctionToolset()


@sketch_toolset.tool
def create_sketch_rectangle(
    plane: str,
    width_mm: float,
    height_mm: float,
    center_x_mm: float = 0,
    center_y_mm: float = 0,
    sketch_name: str = '',
    target_body: str = '',
) -> str:
    """Create a rectangle sketch on a construction plane.

    Use this to start a 2D profile that can be extruded into a 3D body.
    When sketch_name is provided, adds the rectangle to an existing sketch
    instead of creating a new one (for combining primitives on one plane).

    Args:
        plane: Construction plane -- 'xy', 'xz', or 'yz'.
        width_mm: Rectangle width in millimeters.
        height_mm: Rectangle height in millimeters.
        center_x_mm: Center X position in mm (default 0).
        center_y_mm: Center Y position in mm (default 0).
        sketch_name: Optional. Name of an existing sketch to add geometry to.
            Leave empty to create a new sketch.
        target_body: Optional. Name of existing body to cut into. When set,
            the sketch is placed on that body's face for subtraction.
    """
    from ..bridge import dispatch_to_main_thread

    # Convert mm to cm corner coordinates
    x1 = (center_x_mm - width_mm / 2) / 10
    y1 = (center_y_mm - height_mm / 2) / 10
    x2 = (center_x_mm + width_mm / 2) / 10
    y2 = (center_y_mm + height_mm / 2) / 10

    result = dispatch_to_main_thread('create_sketch_rectangle', {
        'plane': plane,
        'x1': x1, 'y1': y1,
        'x2': x2, 'y2': y2,
        'sketch_name': sketch_name or None,
    })
    _check_bridge_result(result, 'create_sketch_rectangle')
    msg = (
        f"Created sketch '{result['sketch_name']}' with "
        f"{width_mm}x{height_mm}mm rectangle "
        f"({result['profile_count']} profiles)"
    )
    if target_body:
        msg += (
            f"\n-> Use extrude(sketch_name='{result['sketch_name']}', "
            f"profile_index=0, operation='cut') to cut into '{target_body}'"
        )
    return msg


@sketch_toolset.tool
def create_sketch_circle(
    plane: str,
    radius_mm: float,
    center_x_mm: float = 0,
    center_y_mm: float = 0,
    sketch_name: str = '',
    target_body: str = '',
) -> str:
    """Create a circle sketch on a construction plane.

    Use this to start a circular 2D profile that can be extruded.
    When sketch_name is provided, adds the circle to an existing sketch
    instead of creating a new one (for combining primitives on one plane).

    Args:
        plane: Construction plane -- 'xy', 'xz', or 'yz'.
        radius_mm: Circle radius in millimeters.
        center_x_mm: Center X position in mm (default 0).
        center_y_mm: Center Y position in mm (default 0).
        sketch_name: Optional. Name of an existing sketch to add geometry to.
            Leave empty to create a new sketch.
        target_body: Optional. Name of existing body to cut into. When set,
            the sketch is placed on that body's face for subtraction.
    """
    from ..bridge import dispatch_to_main_thread

    result = dispatch_to_main_thread('create_sketch_circle', {
        'plane': plane,
        'center_x': center_x_mm / 10,
        'center_y': center_y_mm / 10,
        'radius': radius_mm / 10,
        'sketch_name': sketch_name or None,
    })
    _check_bridge_result(result, 'create_sketch_circle')
    msg = (
        f"Created sketch '{result['sketch_name']}' with "
        f"{radius_mm}mm radius circle "
        f"({result['profile_count']} profiles)"
    )
    if target_body:
        msg += (
            f"\n-> Use extrude(sketch_name='{result['sketch_name']}', "
            f"profile_index=0, operation='cut') to cut into '{target_body}'"
        )
    return msg


@sketch_toolset.tool
def create_sketch_lines_arcs(
    plane: str,
    start_x_mm: float,
    start_y_mm: float,
    segments: list[dict],
    close: bool = True,
    sketch_name: str = '',
) -> str:
    """Create a sketch with connected line and arc segments for custom profiles.

    Use this for L-shaped, T-shaped, curved, or any complex 2D profiles that
    cannot be made with rectangle or circle tools. Draws segments sequentially
    from the start point.

    Set close=False to create an OPEN PATH for sweep operations. Open paths
    are not extrudable -- they define the sweep direction/shape.

    IMPORTANT: All x, y coordinates in segments are ABSOLUTE positions in mm
    on the sketch plane, NOT relative offsets from the previous point.

    Args:
        plane: Construction plane -- 'xy', 'xz', or 'yz'.
        start_x_mm: Starting point X in millimeters.
        start_y_mm: Starting point Y in millimeters.
        segments: List of segment dicts, each with:
            - type: 'line' or 'arc'
            - x: Endpoint X in mm (absolute position)
            - y: Endpoint Y in mm (absolute position)
            - cx: Arc center X in mm (arc segments only)
            - cy: Arc center Y in mm (arc segments only)
        close: If True (default), auto-close profile for extrude/revolve.
            If False, leave path open for sweep operations.
        sketch_name: Optional. Name of an existing sketch to add geometry to.
            Leave empty to create a new sketch.
    """
    from ..bridge import dispatch_to_main_thread

    # Convert all mm coordinates to cm
    segments_cm = []
    for seg in segments:
        seg_cm = {'type': seg['type'], 'x': seg['x'] / 10, 'y': seg['y'] / 10}
        if seg['type'] == 'arc':
            seg_cm['cx'] = seg['cx'] / 10
            seg_cm['cy'] = seg['cy'] / 10
        segments_cm.append(seg_cm)

    result = dispatch_to_main_thread('create_sketch_lines_arcs', {
        'plane': plane,
        'start_x': start_x_mm / 10,
        'start_y': start_y_mm / 10,
        'segments': segments_cm,
        'sketch_name': sketch_name or None,
        'close': close,
    })
    _check_bridge_result(result, 'create_sketch_lines_arcs')
    if close:
        return (
            f"Created sketch '{result['sketch_name']}' with "
            f"{len(segments)} segments "
            f"({result['profile_count']} profiles)"
        )
    else:
        return (
            f"Created open path sketch '{result['sketch_name']}' with "
            f"{len(segments)} segments "
            f"({result['path_count']} curves for sweep)"
        )


@sketch_toolset.tool
def create_sketch_slot(
    plane: str,
    center_x_mm: float,
    center_y_mm: float,
    length_mm: float,
    width_mm: float,
    angle_deg: float = 0,
    sketch_name: str = '',
    target_body: str = '',
) -> str:
    """Create a slot (oblong/stadium) sketch on a construction plane.

    Use this for mounting slots, elongated holes, and oblong cutouts common
    in CNC aluminum parts. The slot has semicircular ends and straight sides.

    Args:
        plane: Construction plane -- 'xy', 'xz', or 'yz'.
        center_x_mm: Slot center X in millimeters.
        center_y_mm: Slot center Y in millimeters.
        length_mm: Total slot length in mm (end to end, including rounded ends).
        width_mm: Total slot width in mm. Must be less than length.
        angle_deg: Rotation angle in degrees (0 = horizontal). Default 0.
        sketch_name: Optional. Name of an existing sketch to add geometry to.
            Leave empty to create a new sketch.
        target_body: Optional. Name of existing body to cut into. When set,
            the sketch is placed on that body's face for subtraction.
    """
    from ..bridge import dispatch_to_main_thread
    import math

    result = dispatch_to_main_thread('create_sketch_slot', {
        'plane': plane,
        'center_x': center_x_mm / 10,
        'center_y': center_y_mm / 10,
        'length': length_mm / 10,
        'width': width_mm / 10,
        'angle_rad': math.radians(angle_deg),
        'sketch_name': sketch_name or None,
    })
    _check_bridge_result(result, 'create_sketch_slot')
    msg = (
        f"Created sketch '{result['sketch_name']}' with "
        f"{length_mm}x{width_mm}mm slot "
        f"({result['profile_count']} profiles)"
    )
    if target_body:
        msg += (
            f"\n-> Use extrude(sketch_name='{result['sketch_name']}', "
            f"profile_index=0, operation='cut') to cut into '{target_body}'"
        )
    return msg


@sketch_toolset.tool
def create_sketch_polygon(
    plane: str,
    center_x_mm: float,
    center_y_mm: float,
    inscribed_radius_mm: float,
    side_count: int,
    angle_deg: float = 0,
    sketch_name: str = '',
    target_body: str = '',
) -> str:
    """Create a regular polygon sketch on a construction plane.

    Use this for hex pockets, pentagonal features, and other regular polygon
    shapes. The inscribed radius is the distance from center to the middle
    of each flat edge -- for hex pockets, this equals the wrench size / 2.

    Args:
        plane: Construction plane -- 'xy', 'xz', or 'yz'.
        center_x_mm: Polygon center X in millimeters.
        center_y_mm: Polygon center Y in millimeters.
        inscribed_radius_mm: Inscribed circle radius in mm (center to flat edge).
        side_count: Number of sides (3 to 12). Use circle tool for >12 sides.
        angle_deg: Rotation angle in degrees (default 0).
        sketch_name: Optional. Name of an existing sketch to add geometry to.
            Leave empty to create a new sketch.
        target_body: Optional. Name of existing body to cut into. When set,
            the sketch is placed on that body's face for subtraction.
    """
    from ..bridge import dispatch_to_main_thread
    import math

    result = dispatch_to_main_thread('create_sketch_polygon', {
        'plane': plane,
        'center_x': center_x_mm / 10,
        'center_y': center_y_mm / 10,
        'inscribed_radius': inscribed_radius_mm / 10,
        'side_count': side_count,
        'angle_rad': math.radians(angle_deg),
        'sketch_name': sketch_name or None,
    })
    _check_bridge_result(result, 'create_sketch_polygon')
    side_names = {3: 'triangle', 4: 'square', 5: 'pentagon', 6: 'hexagon',
                  8: 'octagon'}
    shape = side_names.get(side_count, f'{side_count}-gon')
    msg = (
        f"Created sketch '{result['sketch_name']}' with "
        f"{inscribed_radius_mm}mm {shape} "
        f"({result['profile_count']} profiles)"
    )
    if target_body:
        msg += (
            f"\n-> Use extrude(sketch_name='{result['sketch_name']}', "
            f"profile_index=0, operation='cut') to cut into '{target_body}'"
        )
    return msg
