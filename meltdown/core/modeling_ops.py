"""Fusion API facade for all modeling operations.

Main thread only -- never call from worker threads. These functions receive
Fusion API objects directly and return serializable dicts. The bridge routes
dispatched requests to these functions on the main thread.

All distance and coordinate parameters use centimeters (Fusion's internal unit).
Conversion from user-facing millimeters to centimeters happens at the agent
tool layer, not here.
"""
import math

import adsk.core
import adsk.fusion


def _body_index(comp: adsk.fusion.Component, body: adsk.fusion.BRepBody) -> int:
    """Find the index of a body in a component's bRepBodies collection.

    Args:
        comp: The component containing the bodies.
        body: The body to find.

    Returns:
        The zero-based index of the body.

    Raises:
        ValueError: If the body is not found in the collection.
    """
    for i in range(comp.bRepBodies.count):
        if comp.bRepBodies.item(i) == body:
            return i
    raise ValueError(f'Body not found in component: {body.name}')


def _get_construction_plane(comp: adsk.fusion.Component, plane_name: str):
    """Get a construction plane by name.

    Args:
        comp: The component to get the plane from.
        plane_name: One of 'xy', 'xz', or 'yz'.

    Returns:
        The construction plane object.

    Raises:
        ValueError: If the plane name is not recognized.
    """
    planes = {
        'xy': comp.xYConstructionPlane,
        'xz': comp.xZConstructionPlane,
        'yz': comp.yZConstructionPlane,
    }
    if plane_name not in planes:
        raise ValueError(
            f"Invalid plane_name '{plane_name}'. Must be 'xy', 'xz', or 'yz'."
        )
    return planes[plane_name]


def _get_feature_operation(operation: str) -> int:
    """Map an operation string to a FeatureOperations enum value.

    Args:
        operation: One of 'new', 'join', 'cut', 'intersect'.

    Returns:
        The corresponding adsk.fusion.FeatureOperations value.

    Raises:
        ValueError: If the operation string is not recognized.
    """
    ops = {
        'new': adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
        'join': adsk.fusion.FeatureOperations.JoinFeatureOperation,
        'cut': adsk.fusion.FeatureOperations.CutFeatureOperation,
        'intersect': adsk.fusion.FeatureOperations.IntersectFeatureOperation,
    }
    if operation not in ops:
        raise ValueError(
            f"Invalid operation '{operation}'. Must be one of: {list(ops.keys())}."
        )
    return ops[operation]


def _get_construction_axis(comp: adsk.fusion.Component, direction: str):
    """Get a construction axis by direction name.

    Args:
        comp: The component to get the axis from.
        direction: One of 'x', 'y', or 'z'.

    Returns:
        The construction axis object.

    Raises:
        ValueError: If the direction is not recognized.
    """
    axes = {
        'x': comp.xConstructionAxis,
        'y': comp.yConstructionAxis,
        'z': comp.zConstructionAxis,
    }
    if direction not in axes:
        raise ValueError(
            f"Invalid direction '{direction}'. Must be 'x', 'y', or 'z'."
        )
    return axes[direction]


def _get_body_by_name(comp: adsk.fusion.Component, body_name: str) -> adsk.fusion.BRepBody:
    """Look up a body by name in a component.

    Args:
        comp: The component to search.
        body_name: Exact name of the body.

    Returns:
        The BRepBody object.

    Raises:
        ValueError: If no body matches, with list of available names.
    """
    body = comp.bRepBodies.itemByName(body_name)
    if body is None:
        available = [comp.bRepBodies.item(i).name
                     for i in range(comp.bRepBodies.count)]
        raise ValueError(
            f"No body named '{body_name}' in active component '{comp.name}'. "
            f"Available: {available}"
        )
    return body


def create_sketch_rectangle(design: adsk.fusion.Design, plane_name: str,
                            x1_cm: float, y1_cm: float,
                            x2_cm: float, y2_cm: float,
                            sketch_name: str = None) -> dict:
    """Create a sketch with a two-point rectangle on a construction plane.

    Args:
        design: The active Fusion Design object.
        plane_name: Construction plane -- 'xy', 'xz', or 'yz'.
        x1_cm: First corner X coordinate in centimeters.
        y1_cm: First corner Y coordinate in centimeters.
        x2_cm: Opposite corner X coordinate in centimeters.
        y2_cm: Opposite corner Y coordinate in centimeters.
        sketch_name: Optional name of an existing sketch to add geometry to.
            When provided, plane_name is ignored. When omitted, a new sketch
            is created on the specified plane.

    Returns:
        Dict with keys:
            sketch_name (str): Name of the created sketch.
            profile_count (int): Number of closed profiles in the sketch.
    """
    comp = design.activeComponent
    if sketch_name:
        sketch = comp.sketches.itemByName(sketch_name)
        if sketch is None:
            available = [comp.sketches.item(i).name
                         for i in range(comp.sketches.count)]
            raise ValueError(
                f"Sketch '{sketch_name}' not found in active component "
                f"'{comp.name}'. Available: {available}"
            )
    else:
        plane = _get_construction_plane(comp, plane_name)
        sketch = comp.sketches.add(plane)
    pt1 = adsk.core.Point3D.create(x1_cm, y1_cm, 0)
    pt2 = adsk.core.Point3D.create(x2_cm, y2_cm, 0)
    sketch.sketchCurves.sketchLines.addTwoPointRectangle(pt1, pt2)
    return {
        'sketch_name': sketch.name,
        'profile_count': sketch.profiles.count,
    }


def create_sketch_circle(design: adsk.fusion.Design, plane_name: str,
                          center_x_cm: float, center_y_cm: float,
                          radius_cm: float,
                          sketch_name: str = None) -> dict:
    """Create a sketch with a circle on a construction plane.

    Args:
        design: The active Fusion Design object.
        plane_name: Construction plane -- 'xy', 'xz', or 'yz'.
        center_x_cm: Circle center X coordinate in centimeters.
        center_y_cm: Circle center Y coordinate in centimeters.
        radius_cm: Circle radius in centimeters.
        sketch_name: Optional name of an existing sketch to add geometry to.
            When provided, plane_name is ignored. When omitted, a new sketch
            is created on the specified plane.

    Returns:
        Dict with keys:
            sketch_name (str): Name of the created sketch.
            profile_count (int): Number of closed profiles in the sketch.
    """
    if radius_cm <= 0:
        raise ValueError(f'radius_cm must be positive, got {radius_cm}')

    comp = design.activeComponent
    if sketch_name:
        sketch = comp.sketches.itemByName(sketch_name)
        if sketch is None:
            available = [comp.sketches.item(i).name
                         for i in range(comp.sketches.count)]
            raise ValueError(
                f"Sketch '{sketch_name}' not found in active component "
                f"'{comp.name}'. Available: {available}"
            )
    else:
        plane = _get_construction_plane(comp, plane_name)
        sketch = comp.sketches.add(plane)
    center = adsk.core.Point3D.create(center_x_cm, center_y_cm, 0)
    sketch.sketchCurves.sketchCircles.addByCenterRadius(center, radius_cm)
    return {
        'sketch_name': sketch.name,
        'profile_count': sketch.profiles.count,
    }


def create_sketch_lines_arcs(design: adsk.fusion.Design, plane_name: str,
                              start_x_cm: float, start_y_cm: float,
                              segments: list, sketch_name: str = None,
                              close: bool = True) -> dict:
    """Create a sketch with connected line and arc segments on a construction plane.

    Draws a sequence of line and arc segments starting from (start_x_cm, start_y_cm).
    Each segment connects from the previous endpoint to the specified (x, y).
    When close=True (default), a closing line segment is automatically added from
    the last point back to the start if they are not coincident, ensuring a closed
    extrudable profile. When close=False, the path is left open (for sweep paths).

    Uses SketchPoint chaining (endSketchPoint from one segment feeds into the
    next) to guarantee geometric connectivity between segments.

    Args:
        design: The active Fusion Design object.
        plane_name: Construction plane -- 'xy', 'xz', or 'yz'.
        start_x_cm: Starting point X coordinate in centimeters.
        start_y_cm: Starting point Y coordinate in centimeters.
        segments: List of segment dicts. Each dict has:
            - type (str): 'line' or 'arc'
            - x (float): Endpoint X in centimeters
            - y (float): Endpoint Y in centimeters
            - cx (float): Arc center X in centimeters (arc only)
            - cy (float): Arc center Y in centimeters (arc only)
        sketch_name: Optional name of an existing sketch to add geometry to.
            When provided, plane_name is ignored. When omitted, a new sketch
            is created on the specified plane.
        close: If True (default), auto-close the profile with a line from
            last point to start. If False, leave the path open (for sweep
            paths). When False, returns path_count instead of profile_count.

    Returns:
        Dict with keys:
            sketch_name (str): Name of the sketch.
            profile_count (int): Number of closed profiles (when close=True).
            path_count (int): Number of sketch curves (when close=False).

    Raises:
        ValueError: If segments is empty, segment type is invalid, or
            sketch_name is provided but not found.
    """
    if not segments:
        raise ValueError('segments must not be empty.')

    comp = design.activeComponent
    if sketch_name:
        sketch = comp.sketches.itemByName(sketch_name)
        if sketch is None:
            available = [comp.sketches.item(i).name
                         for i in range(comp.sketches.count)]
            raise ValueError(
                f"Sketch '{sketch_name}' not found in active component "
                f"'{comp.name}'. Available: {available}"
            )
    else:
        plane = _get_construction_plane(comp, plane_name)
        sketch = comp.sketches.add(plane)

    lines = sketch.sketchCurves.sketchLines
    arcs = sketch.sketchCurves.sketchArcs

    current_x, current_y = start_x_cm, start_y_cm
    prev_end_sketch_point = None
    first_sketch_point = None

    for i, seg in enumerate(segments):
        seg_type = seg.get('type')
        if seg_type not in ('line', 'arc'):
            raise ValueError(
                f"Segment {i}: type must be 'line' or 'arc', got '{seg_type}'."
            )
        end_x = seg['x']
        end_y = seg['y']

        if seg_type == 'line':
            if prev_end_sketch_point is not None:
                end_pt = adsk.core.Point3D.create(end_x, end_y, 0)
                entity = lines.addByTwoPoints(prev_end_sketch_point, end_pt)
            else:
                s_pt = adsk.core.Point3D.create(current_x, current_y, 0)
                end_pt = adsk.core.Point3D.create(end_x, end_y, 0)
                entity = lines.addByTwoPoints(s_pt, end_pt)
                first_sketch_point = entity.startSketchPoint

            prev_end_sketch_point = entity.endSketchPoint

        elif seg_type == 'arc':
            cx = seg['cx']
            cy = seg['cy']
            start_angle = math.atan2(current_y - cy, current_x - cx)
            end_angle = math.atan2(end_y - cy, end_x - cx)
            sweep = end_angle - start_angle
            if sweep <= 0:
                sweep += 2 * math.pi

            center_pt = adsk.core.Point3D.create(cx, cy, 0)
            if prev_end_sketch_point is not None:
                entity = arcs.addByCenterStartSweep(
                    center_pt, prev_end_sketch_point, sweep
                )
            else:
                s_pt = adsk.core.Point3D.create(current_x, current_y, 0)
                entity = arcs.addByCenterStartSweep(center_pt, s_pt, sweep)
                first_sketch_point = entity.startSketchPoint

            prev_end_sketch_point = entity.endSketchPoint

        current_x, current_y = end_x, end_y

    # Auto-close (D-04): add closing line if last point is not coincident
    # with start point. Only when close=True (D-01).
    if close:
        TOLERANCE = 1e-6  # cm (~0.01 microns)
        if (abs(current_x - start_x_cm) > TOLERANCE or
                abs(current_y - start_y_cm) > TOLERANCE):
            if first_sketch_point is not None and prev_end_sketch_point is not None:
                lines.addByTwoPoints(prev_end_sketch_point, first_sketch_point)
            elif prev_end_sketch_point is not None:
                close_end = adsk.core.Point3D.create(start_x_cm, start_y_cm, 0)
                lines.addByTwoPoints(prev_end_sketch_point, close_end)

    if close:
        return {
            'sketch_name': sketch.name,
            'profile_count': sketch.profiles.count,
        }
    else:
        return {
            'sketch_name': sketch.name,
            'path_count': sketch.sketchCurves.count,
        }


def create_sketch_slot(design: adsk.fusion.Design, plane_name: str,
                        center_x_cm: float, center_y_cm: float,
                        length_cm: float, width_cm: float,
                        angle_rad: float = 0, sketch_name: str = None) -> dict:
    """Create a sketch with a center-point slot on a construction plane.

    Draws an oblong slot (stadium shape) defined by center point, total length,
    total width, and rotation angle. The semicircular ends have radius = width/2.

    Uses Fusion's addCenterPointSlot API when available (Nov 2025+), with a
    manual fallback (two lines + two arcs) for older Fusion builds.

    Args:
        design: The active Fusion Design object.
        plane_name: Construction plane -- 'xy', 'xz', or 'yz'.
        center_x_cm: Slot center X coordinate in centimeters.
        center_y_cm: Slot center Y coordinate in centimeters.
        length_cm: Total slot length in centimeters (end to end).
        width_cm: Total slot width in centimeters.
        angle_rad: Rotation angle in radians (0 = horizontal). Default 0.
        sketch_name: Optional name of an existing sketch to add geometry to.

    Returns:
        Dict with keys:
            sketch_name (str): Name of the sketch.
            profile_count (int): Number of closed profiles in the sketch.

    Raises:
        ValueError: If length or width is not positive, or width >= length.
    """
    if length_cm <= 0:
        raise ValueError(f'length_cm must be positive, got {length_cm}')
    if width_cm <= 0:
        raise ValueError(f'width_cm must be positive, got {width_cm}')
    if width_cm >= length_cm:
        raise ValueError(
            f'width_cm ({width_cm}) must be less than length_cm ({length_cm}). '
            f'For a circle, use create_sketch_circle instead.'
        )

    comp = design.activeComponent
    if sketch_name:
        sketch = comp.sketches.itemByName(sketch_name)
        if sketch is None:
            available = [comp.sketches.item(i).name
                         for i in range(comp.sketches.count)]
            raise ValueError(
                f"Sketch '{sketch_name}' not found in active component "
                f"'{comp.name}'. Available: {available}"
            )
    else:
        plane = _get_construction_plane(comp, plane_name)
        sketch = comp.sketches.add(plane)

    half_length = length_cm / 2
    end_x = center_x_cm + half_length * math.cos(angle_rad)
    end_y = center_y_cm + half_length * math.sin(angle_rad)

    center_pt = adsk.core.Point3D.create(center_x_cm, center_y_cm, 0)
    end_pt = adsk.core.Point3D.create(end_x, end_y, 0)
    width_val = adsk.core.ValueInput.createByReal(width_cm)

    try:
        sketch.addCenterPointSlot(center_pt, end_pt, width_val, False)
    except AttributeError:
        # Fallback for older Fusion builds (pre-Nov 2025) that lack
        # addCenterPointSlot. Manually draw two parallel lines + two arcs.
        _draw_slot_manual(sketch, center_x_cm, center_y_cm,
                          length_cm, width_cm, angle_rad)

    return {
        'sketch_name': sketch.name,
        'profile_count': sketch.profiles.count,
    }


def _draw_slot_manual(sketch, center_x_cm: float, center_y_cm: float,
                       length_cm: float, width_cm: float, angle_rad: float):
    """Manual slot construction fallback using lines and arcs.

    Draws a stadium shape: two parallel lines connected by two semicircular arcs.
    """
    half_length = length_cm / 2
    half_width = width_cm / 2
    # Inner half-length is the straight portion (total - end radii)
    inner_half = half_length - half_width

    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    # Perpendicular direction
    cos_p = math.cos(angle_rad + math.pi / 2)
    sin_p = math.sin(angle_rad + math.pi / 2)

    # Four corners of the straight sections
    # Right-top, right-bottom, left-bottom, left-top
    rt_x = center_x_cm + inner_half * cos_a + half_width * cos_p
    rt_y = center_y_cm + inner_half * sin_a + half_width * sin_p
    rb_x = center_x_cm + inner_half * cos_a - half_width * cos_p
    rb_y = center_y_cm + inner_half * sin_a - half_width * sin_p
    lb_x = center_x_cm - inner_half * cos_a - half_width * cos_p
    lb_y = center_y_cm - inner_half * sin_a - half_width * sin_p
    lt_x = center_x_cm - inner_half * cos_a + half_width * cos_p
    lt_y = center_y_cm - inner_half * sin_a + half_width * sin_p

    # Arc centers (at the ends of the straight sections)
    rc_x = center_x_cm + inner_half * cos_a
    rc_y = center_y_cm + inner_half * sin_a
    lc_x = center_x_cm - inner_half * cos_a
    lc_y = center_y_cm - inner_half * sin_a

    lines = sketch.sketchCurves.sketchLines
    arcs_coll = sketch.sketchCurves.sketchArcs

    # Top line (left-top to right-top)
    lt_pt = adsk.core.Point3D.create(lt_x, lt_y, 0)
    rt_pt = adsk.core.Point3D.create(rt_x, rt_y, 0)
    top_line = lines.addByTwoPoints(lt_pt, rt_pt)

    # Right arc (right-top to right-bottom, center at rc)
    rc_pt = adsk.core.Point3D.create(rc_x, rc_y, 0)
    right_arc = arcs_coll.addByCenterStartSweep(
        rc_pt, top_line.endSketchPoint, math.pi
    )

    # Bottom line (right-bottom to left-bottom)
    lb_pt = adsk.core.Point3D.create(lb_x, lb_y, 0)
    bottom_line = lines.addByTwoPoints(right_arc.endSketchPoint, lb_pt)

    # Left arc (left-bottom to left-top, center at lc)
    lc_pt = adsk.core.Point3D.create(lc_x, lc_y, 0)
    arcs_coll.addByCenterStartSweep(
        lc_pt, bottom_line.endSketchPoint, math.pi
    )


def create_sketch_polygon(design: adsk.fusion.Design, plane_name: str,
                           center_x_cm: float, center_y_cm: float,
                           inscribed_radius_cm: float, side_count: int,
                           angle_rad: float = 0,
                           sketch_name: str = None) -> dict:
    """Create a sketch with a regular polygon on a construction plane.

    Draws an inscribed regular polygon (all vertices touch a circle of the
    given radius). Supports 3 to 12 sides. For CNC hex pockets, the
    inscribed radius equals the flat-to-flat distance / 2.

    Args:
        design: The active Fusion Design object.
        plane_name: Construction plane -- 'xy', 'xz', or 'yz'.
        center_x_cm: Polygon center X coordinate in centimeters.
        center_y_cm: Polygon center Y coordinate in centimeters.
        inscribed_radius_cm: Inscribed circle radius in centimeters.
        side_count: Number of sides (3-12). Use circle tool for >12.
        angle_rad: Rotation angle in radians (default 0). 0 means one flat
            edge at the bottom (Fusion's default orientation).
        sketch_name: Optional name of an existing sketch to add geometry to.

    Returns:
        Dict with keys:
            sketch_name (str): Name of the sketch.
            profile_count (int): Number of closed profiles in the sketch.

    Raises:
        ValueError: If side_count is outside 3-12 range or radius is not positive.
    """
    if side_count < 3 or side_count > 12:
        raise ValueError(
            f"side_count must be 3-12, got {side_count}. "
            f"Use create_sketch_circle for near-circular shapes."
        )
    if inscribed_radius_cm <= 0:
        raise ValueError(
            f'inscribed_radius_cm must be positive, got {inscribed_radius_cm}'
        )

    comp = design.activeComponent
    if sketch_name:
        sketch = comp.sketches.itemByName(sketch_name)
        if sketch is None:
            available = [comp.sketches.item(i).name
                         for i in range(comp.sketches.count)]
            raise ValueError(
                f"Sketch '{sketch_name}' not found in active component "
                f"'{comp.name}'. Available: {available}"
            )
    else:
        plane = _get_construction_plane(comp, plane_name)
        sketch = comp.sketches.add(plane)

    center_pt = adsk.core.Point3D.create(center_x_cm, center_y_cm, 0)
    sketch.sketchCurves.sketchLines.addScribedPolygon(
        center_pt, side_count, angle_rad, inscribed_radius_cm, True
    )

    return {
        'sketch_name': sketch.name,
        'profile_count': sketch.profiles.count,
    }


def extrude_profile(design: adsk.fusion.Design, sketch_name: str,
                    profile_index: int, distance_cm: float,
                    operation: str = 'new') -> dict:
    """Extrude a sketch profile by a given distance.

    For cut, join, and intersect operations, the extrusion must intersect an
    existing body. If the initial direction misses, the function automatically
    retries with the opposite direction (negated distance). This handles the
    common case where a sketch on a construction plane has its normal pointing
    away from the target body.

    Args:
        design: The active Fusion Design object.
        sketch_name: Name of the sketch containing the profile.
        profile_index: Zero-based index of the profile to extrude.
        distance_cm: Extrusion distance in centimeters. Positive extrudes
            in the normal direction, negative in the reverse direction.
        operation: Feature operation -- 'new', 'join', 'cut', or 'intersect'.

    Returns:
        Dict with keys:
            feature_name (str): Name of the extrude feature.
            body_name (str): Name of the resulting body.
            body_index (int): Index of the body in active component bRepBodies.
            face_count (int): Number of faces on the resulting body.
            edge_count (int): Number of edges on the resulting body.
            timeline_index (int): Timeline position of the feature.
    """
    comp = design.activeComponent

    # Find the sketch by name
    sketch = comp.sketches.itemByName(sketch_name)
    if sketch is None:
        raise ValueError(f"Sketch '{sketch_name}' not found.")

    if profile_index < 0 or profile_index >= sketch.profiles.count:
        raise ValueError(
            f'profile_index {profile_index} out of range. '
            f'Sketch has {sketch.profiles.count} profile(s).'
        )

    profile = sketch.profiles.item(profile_index)
    op = _get_feature_operation(operation)
    needs_body = operation in ('cut', 'join', 'intersect')

    # For operations that require an existing body, try both extrusion
    # directions. The sketch normal direction is fixed for construction
    # planes, so the caller may not know which direction reaches the body.
    distances_to_try = [distance_cm]
    if needs_body:
        distances_to_try.append(-distance_cm)

    last_error = None
    for dist in distances_to_try:
        try:
            dist_val = adsk.core.ValueInput.createByReal(dist)
            extrude = comp.features.extrudeFeatures.addSimple(
                profile, dist_val, op,
            )
        except Exception as e:
            last_error = e
            continue

        # Verify the feature produced at least one body.
        # A cut that misses the target body may create an unhealthy feature
        # with zero resulting bodies -- roll it back before trying the
        # opposite direction.
        if extrude.bodies.count == 0:
            last_error = RuntimeError(
                f"Extrude '{operation}' created a feature but produced no "
                f"bodies. The profile may not intersect any existing body."
            )
            try:
                extrude.deleteMe()
            except Exception:
                pass  # Best-effort cleanup; feature may already be invalid
            continue

        body = extrude.bodies.item(0)
        body_idx = _body_index(comp, body)

        return {
            'feature_name': extrude.name,
            'body_name': body.name,
            'body_index': body_idx,
            'face_count': body.faces.count,
            'edge_count': body.edges.count,
            'timeline_index': extrude.timelineObject.index,
        }

    # Both directions failed -- raise the last error with context
    raise RuntimeError(
        f"Extrude '{operation}' failed in both directions for sketch "
        f"'{sketch_name}' profile {profile_index}. "
        f"The profile may not overlap any existing body. "
        f"Last error: {last_error}"
    )


def fillet_edges(design: adsk.fusion.Design, body_name: str,
                 edge_indices: list, radius_cm: float) -> dict:
    """Apply a constant-radius fillet to specified edges of a body.

    Args:
        design: The active Fusion Design object.
        body_name: Name of the body in the active component.
        edge_indices: List of zero-based edge indices to fillet.
        radius_cm: Fillet radius in centimeters.

    Returns:
        Dict with keys:
            feature_name (str): Name of the fillet feature.
            body_name (str): Name of the affected body.
            face_count (int): Number of faces after the operation.
            edge_count (int): Number of edges after the operation.
            timeline_index (int): Timeline position of the feature.
    """
    comp = design.activeComponent
    body = _get_body_by_name(comp, body_name)

    if radius_cm <= 0:
        raise ValueError(f'radius_cm must be positive, got {radius_cm}')
    if not edge_indices:
        raise ValueError('edge_indices must not be empty.')

    edge_collection = adsk.core.ObjectCollection.create()
    for idx in edge_indices:
        if idx < 0 or idx >= body.edges.count:
            raise ValueError(
                f"Edge index {idx} out of range. "
                f"Body '{body_name}' has {body.edges.count} edge(s)."
            )
        edge_collection.add(body.edges.item(idx))

    fillets = comp.features.filletFeatures
    fillet_input = fillets.createInput()
    radius_val = adsk.core.ValueInput.createByReal(radius_cm)
    fillet_input.addConstantRadiusEdgeSet(edge_collection, radius_val, True)
    fillet = fillets.add(fillet_input)

    return {
        'feature_name': fillet.name,
        'body_name': body.name,
        'face_count': body.faces.count,
        'edge_count': body.edges.count,
        'timeline_index': fillet.timelineObject.index,
    }


def chamfer_edges(design: adsk.fusion.Design, body_name: str,
                  edge_indices: list, distance_cm: float) -> dict:
    """Apply an equal-distance chamfer to specified edges of a body.

    Args:
        design: The active Fusion Design object.
        body_name: Name of the body in the active component.
        edge_indices: List of zero-based edge indices to chamfer.
        distance_cm: Chamfer distance in centimeters.

    Returns:
        Dict with keys:
            feature_name (str): Name of the chamfer feature.
            body_name (str): Name of the affected body.
            face_count (int): Number of faces after the operation.
            edge_count (int): Number of edges after the operation.
            timeline_index (int): Timeline position of the feature.
    """
    comp = design.activeComponent
    body = _get_body_by_name(comp, body_name)

    if distance_cm <= 0:
        raise ValueError(f'distance_cm must be positive, got {distance_cm}')
    if not edge_indices:
        raise ValueError('edge_indices must not be empty.')

    edge_collection = adsk.core.ObjectCollection.create()
    for idx in edge_indices:
        if idx < 0 or idx >= body.edges.count:
            raise ValueError(
                f"Edge index {idx} out of range. "
                f"Body '{body_name}' has {body.edges.count} edge(s)."
            )
        edge_collection.add(body.edges.item(idx))

    chamfers = comp.features.chamferFeatures
    distance_val = adsk.core.ValueInput.createByReal(distance_cm)
    chamfer_input = chamfers.createInput2()
    chamfer_input.chamferType = adsk.fusion.ChamferTypes.EqualDistanceChamferType
    chamfer_input.addEqualDistanceChamferEdgeSet(edge_collection, distance_val, True)
    chamfer = chamfers.add(chamfer_input)

    return {
        'feature_name': chamfer.name,
        'body_name': body.name,
        'face_count': body.faces.count,
        'edge_count': body.edges.count,
        'timeline_index': chamfer.timelineObject.index,
    }


def shell_body(design: adsk.fusion.Design, body_name: str,
               face_indices_to_remove: list,
               thickness_cm: float) -> dict:
    """Shell a body by removing specified faces and applying a wall thickness.

    Args:
        design: The active Fusion Design object.
        body_name: Name of the body in the active component.
        face_indices_to_remove: List of zero-based face indices to remove
            (these become the open faces of the shell).
        thickness_cm: Wall thickness in centimeters.

    Returns:
        Dict with keys:
            feature_name (str): Name of the shell feature.
            body_name (str): Name of the affected body.
            face_count (int): Number of faces after the operation.
            edge_count (int): Number of edges after the operation.
            timeline_index (int): Timeline position of the feature.
    """
    comp = design.activeComponent
    body = _get_body_by_name(comp, body_name)

    if thickness_cm <= 0:
        raise ValueError(f'thickness_cm must be positive, got {thickness_cm}')
    if not face_indices_to_remove:
        raise ValueError('face_indices_to_remove must not be empty.')

    face_collection = adsk.core.ObjectCollection.create()
    for idx in face_indices_to_remove:
        if idx < 0 or idx >= body.faces.count:
            raise ValueError(
                f"Face index {idx} out of range. "
                f"Body '{body_name}' has {body.faces.count} face(s)."
            )
        face_collection.add(body.faces.item(idx))

    shells = comp.features.shellFeatures
    shell_input = shells.createInput(face_collection)
    thickness_val = adsk.core.ValueInput.createByReal(thickness_cm)
    shell_input.insideThickness = thickness_val
    shell = shells.add(shell_input)

    return {
        'feature_name': shell.name,
        'body_name': body.name,
        'face_count': body.faces.count,
        'edge_count': body.edges.count,
        'timeline_index': shell.timelineObject.index,
    }


def create_holes(design: adsk.fusion.Design, face_index: int,
                 body_name: str, points_cm: list,
                 diameter_cm: float, depth_cm: float) -> dict:
    """Create simple holes at specified points on a body face.

    Args:
        design: The active Fusion Design object.
        face_index: Zero-based index of the face on the body to place holes on.
        body_name: Name of the body in the active component.
        points_cm: List of [x, y] coordinate pairs in centimeters, relative
            to the face's sketch coordinate system.
        diameter_cm: Hole diameter in centimeters.
        depth_cm: Hole depth in centimeters.

    Returns:
        Dict with keys:
            feature_name (str): Name of the hole feature.
            hole_count (int): Number of holes created.
            timeline_index (int): Timeline position of the feature.
    """
    comp = design.activeComponent
    body = _get_body_by_name(comp, body_name)

    if diameter_cm <= 0:
        raise ValueError(f'diameter_cm must be positive, got {diameter_cm}')
    if depth_cm <= 0:
        raise ValueError(f'depth_cm must be positive, got {depth_cm}')
    if not points_cm:
        raise ValueError('points_cm must not be empty.')

    if face_index < 0 or face_index >= body.faces.count:
        raise ValueError(
            f"Face index {face_index} out of range. "
            f"Body '{body_name}' has {body.faces.count} face(s)."
        )

    face = body.faces.item(face_index)

    # Create a sketch on the target face for hole placement
    sketch = comp.sketches.add(face)
    for point in points_cm:
        if len(point) < 2:
            raise ValueError(
                f'Each point must have at least 2 coordinates [x, y], got {point}'
            )
        pt = adsk.core.Point3D.create(point[0], point[1], 0)
        sketch.sketchPoints.add(pt)

    # Collect the sketch points (skip the origin point at index 0)
    sketch_points = adsk.core.ObjectCollection.create()
    for i in range(1, sketch.sketchPoints.count):
        sketch_points.add(sketch.sketchPoints.item(i))

    holes = comp.features.holeFeatures
    diameter_val = adsk.core.ValueInput.createByReal(diameter_cm)
    hole_input = holes.createSimpleInput(diameter_val)
    hole_input.setPositionBySketchPoints(sketch_points)
    depth_val = adsk.core.ValueInput.createByReal(depth_cm)
    hole_input.setDistanceExtent(depth_val)
    hole = holes.add(hole_input)

    return {
        'feature_name': hole.name,
        'hole_count': len(points_cm),
        'timeline_index': hole.timelineObject.index,
    }


def combine_bodies(design: adsk.fusion.Design, target_body_name: str,
                   tool_body_names: list, operation: str = 'join',
                   keep_tools: bool = False) -> dict:
    """Combine bodies using a boolean operation (join, cut, or intersect).

    Args:
        design: The active Fusion Design object.
        target_body_name: Name of the target body in the active component.
        tool_body_names: List of tool body names in the active component.
        operation: Boolean operation -- 'join', 'cut', or 'intersect'.
        keep_tools: If True, tool bodies are preserved after the operation.

    Returns:
        Dict with keys:
            feature_name (str): Name of the combine feature.
            body_name (str): Name of the resulting body.
            face_count (int): Number of faces after the operation.
            edge_count (int): Number of edges after the operation.
            timeline_index (int): Timeline position of the feature.
    """
    comp = design.activeComponent
    target_body = _get_body_by_name(comp, target_body_name)

    if not tool_body_names:
        raise ValueError('tool_body_names must not be empty.')

    tool_bodies = adsk.core.ObjectCollection.create()
    for name in tool_body_names:
        tool_bodies.add(_get_body_by_name(comp, name))

    op = _get_feature_operation(operation)

    combines = comp.features.combineFeatures
    combine_input = combines.createInput(target_body, tool_bodies)
    combine_input.operation = op
    combine_input.isKeepToolBodies = keep_tools
    combine = combines.add(combine_input)

    return {
        'feature_name': combine.name,
        'body_name': target_body.name,
        'face_count': target_body.faces.count,
        'edge_count': target_body.edges.count,
        'timeline_index': combine.timelineObject.index,
    }


def rectangular_pattern(design: adsk.fusion.Design, body_name: str,
                        x_count: int, x_spacing_cm: float,
                        y_count: int = 1, y_spacing_cm: float = 0,
                        direction_one: str = 'x',
                        direction_two: str = 'y') -> dict:
    """Create a rectangular pattern of a body along one or two directions.

    Args:
        design: The active Fusion Design object.
        body_name: Name of the body to pattern in the active component.
        x_count: Number of instances along the first direction (including original).
        x_spacing_cm: Spacing between instances in centimeters along direction one.
        y_count: Number of instances along the second direction (default 1, no pattern).
        y_spacing_cm: Spacing in centimeters along direction two (default 0).
        direction_one: First pattern direction -- 'x', 'y', or 'z'.
        direction_two: Second pattern direction -- 'x', 'y', or 'z'.

    Returns:
        Dict with keys:
            feature_name (str): Name of the pattern feature.
            timeline_index (int): Timeline position of the feature.
    """
    comp = design.activeComponent
    body = _get_body_by_name(comp, body_name)

    if x_count < 1:
        raise ValueError(f'x_count must be at least 1, got {x_count}')
    if y_count < 1:
        raise ValueError(f'y_count must be at least 1, got {y_count}')

    input_entities = adsk.core.ObjectCollection.create()
    input_entities.add(body)

    axis_one = _get_construction_axis(comp, direction_one)
    axis_two = _get_construction_axis(comp, direction_two)

    patterns = comp.features.rectangularPatternFeatures
    pattern_input = patterns.createInput(
        input_entities,
        axis_one,
        adsk.core.ValueInput.createByReal(x_count),
        adsk.core.ValueInput.createByReal(x_spacing_cm),
        adsk.fusion.PatternDistanceType.SpacingPatternDistanceType,
    )

    if y_count > 1:
        pattern_input.setDirectionTwo(
            axis_two,
            adsk.core.ValueInput.createByReal(y_count),
            adsk.core.ValueInput.createByReal(y_spacing_cm),
        )

    pattern = patterns.add(pattern_input)

    return {
        'feature_name': pattern.name,
        'timeline_index': pattern.timelineObject.index,
    }


# Thread database constants for ISO Metric thread support (M3-M8)
_METRIC_THREAD_TYPE = 'ISO Metric profile'
_VALID_THREAD_SIZES = {'M3', 'M4', 'M5', 'M6', 'M7', 'M8'}


def add_thread(design: adsk.fusion.Design, body_name: str,
               face_index: int, thread_size: str,
               is_internal: bool = True, full_length: bool = True) -> dict:
    """Add a standard metric thread to a cylindrical face on a body.

    Resolves a human-friendly thread size (e.g., 'M5') to the full ISO Metric
    thread designation via Fusion's ThreadDataQuery database. Validates that
    the target face is cylindrical before applying the thread.

    Supports M3 through M8 (standard coarse pitch). Uses ThreadInfo.create
    with a fallback to the deprecated createThreadInfo for older Fusion builds.

    Args:
        design: The active Fusion Design object.
        body_name: Name of the body in the active component.
        face_index: Zero-based index of the cylindrical face to thread.
        thread_size: Thread size in human-friendly format, e.g., 'M5'.
            Supported sizes: M3, M4, M5, M6, M7, M8.
        is_internal: If True (default), creates an internal thread (tapped hole).
            If False, creates an external thread.
        full_length: If True (default), thread runs the full length of the
            cylindrical face. If False, uses Fusion's default thread length.

    Returns:
        Dict with keys:
            feature_name (str): Name of the thread feature.
            body_name (str): Name of the body.
            thread_size (str): Normalized thread size (e.g., 'M5').
            designation (str): Full thread designation (e.g., 'M5x0.8').
            is_internal (bool): Whether thread is internal.
            face_count (int): Number of faces on the body after threading.
            edge_count (int): Number of edges on the body after threading.
            timeline_index (int): Timeline position of the feature.

    Raises:
        ValueError: If thread size is unsupported, face is not cylindrical,
            face index is out of range, or thread database lookup fails.
    """
    comp = design.activeComponent
    body = _get_body_by_name(comp, body_name)

    # Validate thread size
    size_upper = thread_size.upper()
    if size_upper not in _VALID_THREAD_SIZES:
        raise ValueError(
            f"Thread size '{thread_size}' not supported. "
            f"Must be one of: {sorted(_VALID_THREAD_SIZES)}"
        )

    # Validate face index
    if face_index < 0 or face_index >= body.faces.count:
        raise ValueError(
            f"Face index {face_index} out of range. "
            f"Body '{body_name}' has {body.faces.count} face(s)."
        )

    # Validate cylindrical surface
    face = body.faces.item(face_index)
    if face.geometry.surfaceType != 1:  # CylinderSurfaceType = 1
        cyl_faces = [i for i in range(body.faces.count)
                     if body.faces.item(i).geometry.surfaceType == 1]
        raise ValueError(
            f"Face {face_index} is not cylindrical (required for threads). "
            f"Cylindrical faces on '{body_name}': "
            f"{cyl_faces if cyl_faces else 'none found'}"
        )

    # Query thread database for ISO Metric thread info
    thread_features = comp.features.threadFeatures
    query = thread_features.threadDataQuery
    all_sizes = query.allSizes(_METRIC_THREAD_TYPE)

    # Find matching size (e.g., "M5" in the database size list)
    matching_size = None
    for s in all_sizes:
        if s.upper() == size_upper or s.upper().startswith(size_upper):
            matching_size = s
            break
    if matching_size is None:
        raise ValueError(
            f"Thread size '{thread_size}' not found in Fusion thread database."
        )

    # Get standard coarse pitch designation (first in list)
    designations = query.allDesignations(_METRIC_THREAD_TYPE, matching_size)
    if not designations:
        raise ValueError(f"No designations found for {matching_size}.")
    designation = designations[0]

    # Get thread class
    classes = query.allClasses(is_internal, _METRIC_THREAD_TYPE, designation)
    if not classes:
        raise ValueError(f"No thread classes found for {designation}.")
    thread_class = classes[0]

    # Create ThreadInfo with fallback for older Fusion builds (per D-08)
    try:
        thread_info = adsk.fusion.ThreadInfo.create(
            False, is_internal, _METRIC_THREAD_TYPE,
            designation, thread_class, True
        )
    except AttributeError:
        thread_info = thread_features.createThreadInfo(
            is_internal, _METRIC_THREAD_TYPE,
            designation, thread_class
        )

    # Apply thread to the cylindrical face
    faces_collection = adsk.core.ObjectCollection.create()
    faces_collection.add(face)
    thread_input = thread_features.createInput(faces_collection, thread_info)
    thread_input.isFullLength = full_length

    thread = thread_features.add(thread_input)

    return {
        'feature_name': thread.name,
        'body_name': body.name,
        'thread_size': size_upper,
        'designation': designation,
        'is_internal': is_internal,
        'face_count': body.faces.count,
        'edge_count': body.edges.count,
        'timeline_index': thread.timelineObject.index,
    }


def mirror_body(design: adsk.fusion.Design, body_name: str,
                plane_name: str, operation: str = 'new') -> dict:
    """Create a mirrored copy of a body across a construction plane.

    Args:
        design: The active Fusion Design object.
        body_name: Name of the body to mirror in the active component.
        plane_name: Construction plane -- 'xy', 'xz', or 'yz'.
        operation: Mirror operation -- 'new' (independent copy) or 'join'
            (merge mirrored body with original). Only 'new' and 'join'
            are supported for mirror.

    Returns:
        Dict with keys:
            feature_name (str): Name of the mirror feature.
            body_name (str): Name of the resulting body.
            body_index (int): Index of the body in active component bRepBodies.
            face_count (int): Number of faces on the resulting body.
            edge_count (int): Number of edges on the resulting body.
            timeline_index (int): Timeline position of the feature.

    Raises:
        ValueError: If operation is not 'new' or 'join', body not found,
            or plane name is invalid.
    """
    comp = design.activeComponent

    if operation not in ('new', 'join'):
        raise ValueError(
            f"Invalid mirror operation '{operation}'. Must be 'new' or 'join'."
        )

    body = _get_body_by_name(comp, body_name)
    plane = _get_construction_plane(comp, plane_name)

    input_entities = adsk.core.ObjectCollection.create()
    input_entities.add(body)

    mirror_input = comp.features.mirrorFeatures.createInput(input_entities, plane)
    if operation == 'join':
        mirror_input.isCombine = True

    mirror_feature = comp.features.mirrorFeatures.add(mirror_input)

    result_body = mirror_feature.bodies.item(0)
    return {
        'feature_name': mirror_feature.name,
        'body_name': result_body.name,
        'body_index': _body_index(comp, result_body),
        'face_count': result_body.faces.count,
        'edge_count': result_body.edges.count,
        'timeline_index': mirror_feature.timelineObject.index,
    }


def revolve_profile(design: adsk.fusion.Design, sketch_name: str,
                    profile_index: int, axis: str, angle_rad: float,
                    operation: str = 'new') -> dict:
    """Revolve a sketch profile around a construction axis by a specified angle.

    Creates rotational geometry by revolving a closed sketch profile around
    one of the principal construction axes (x, y, or z). Supports all four
    feature operations (new, join, cut, intersect).

    Args:
        design: The active Fusion Design object.
        sketch_name: Name of the sketch containing the profile to revolve.
        profile_index: Zero-based index of the profile within the sketch.
        axis: Construction axis direction -- 'x', 'y', or 'z'.
        angle_rad: Revolve angle in radians. Use math.pi * 2 for a full
            360-degree revolution.
        operation: Feature operation -- 'new', 'join', 'cut', or 'intersect'.

    Returns:
        Dict with keys:
            feature_name (str): Name of the revolve feature.
            body_name (str): Name of the resulting body.
            body_index (int): Index of the body in active component bRepBodies.
            face_count (int): Number of faces on the resulting body.
            edge_count (int): Number of edges on the resulting body.
            timeline_index (int): Timeline position of the feature.

    Raises:
        ValueError: If sketch not found, profile_index out of range,
            axis invalid, or operation invalid.
    """
    comp = design.activeComponent

    sketch = comp.sketches.itemByName(sketch_name)
    if sketch is None:
        raise ValueError(f"Sketch '{sketch_name}' not found.")

    if profile_index < 0 or profile_index >= sketch.profiles.count:
        raise ValueError(
            f'profile_index {profile_index} out of range. '
            f'Sketch has {sketch.profiles.count} profile(s).'
        )

    profile = sketch.profiles.item(profile_index)
    axis_obj = _get_construction_axis(comp, axis)
    op = _get_feature_operation(operation)

    revolves = comp.features.revolveFeatures
    rev_input = revolves.createInput(profile, axis_obj, op)
    angle_val = adsk.core.ValueInput.createByReal(angle_rad)
    rev_input.setAngleExtent(False, angle_val)

    revolve = revolves.add(rev_input)

    body = revolve.bodies.item(0)
    return {
        'feature_name': revolve.name,
        'body_name': body.name,
        'body_index': _body_index(comp, body),
        'face_count': body.faces.count,
        'edge_count': body.edges.count,
        'timeline_index': revolve.timelineObject.index,
    }


def sweep_profile(design: adsk.fusion.Design, profile_sketch_name: str,
                  path_sketch_name: str, operation: str = 'cut') -> dict:
    """Sweep a profile along a path to create solid geometry.

    Creates geometry by sweeping a closed sketch profile along an open path
    defined by connected sketch curves. The profile plane must be perpendicular
    to the path at its start point.

    Args:
        design: The active Fusion Design object.
        profile_sketch_name: Name of the sketch containing the closed profile.
        path_sketch_name: Name of the sketch containing the open path
            (created with create_sketch_lines_arcs close=False).
        operation: Feature operation -- 'new', 'join', 'cut' (default),
            or 'intersect'. Default is 'cut' for CNC channel/groove workflows.

    Returns:
        Dict with keys:
            feature_name (str): Name of the sweep feature.
            body_name (str): Name of the resulting body.
            face_count (int): Number of faces on the resulting body.
            edge_count (int): Number of edges on the resulting body.
            timeline_index (int): Timeline position of the feature.

    Raises:
        ValueError: If profile sketch not found, has no profiles,
            path sketch not found, has no curves, or operation is invalid.
    """
    comp = design.activeComponent

    # Look up profile sketch
    profile_sketch = comp.sketches.itemByName(profile_sketch_name)
    if profile_sketch is None:
        raise ValueError(f"Profile sketch '{profile_sketch_name}' not found.")
    if profile_sketch.profiles.count == 0:
        raise ValueError(
            f"Profile sketch '{profile_sketch_name}' has no closed profiles. "
            f"Ensure the sketch contains a closed shape (rectangle, circle, etc.)."
        )
    profile = profile_sketch.profiles.item(0)

    # Look up path sketch and extract first curve for createPath
    path_sketch = comp.sketches.itemByName(path_sketch_name)
    if path_sketch is None:
        raise ValueError(f"Path sketch '{path_sketch_name}' not found.")
    if path_sketch.sketchCurves.count == 0:
        raise ValueError(
            f"Path sketch '{path_sketch_name}' has no curves. "
            f"Create a path using create_sketch_lines_arcs with close=False."
        )
    first_curve = path_sketch.sketchCurves.item(0)

    # Create path -- isChain=True (default) auto-discovers connected curves
    path = comp.features.createPath(first_curve)

    # Create and execute sweep
    op = _get_feature_operation(operation)
    sweeps = comp.features.sweepFeatures
    sweep_input = sweeps.createInput(profile, path, op)
    sweep = sweeps.add(sweep_input)

    body = sweep.bodies.item(0)
    return {
        'feature_name': sweep.name,
        'body_name': body.name,
        'face_count': body.faces.count,
        'edge_count': body.edges.count,
        'timeline_index': sweep.timelineObject.index,
    }
