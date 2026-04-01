"""Fusion API facade for state queries and geometry identification.

Main thread only -- never call from worker threads. These functions receive
Fusion API objects directly and return serializable dicts. The bridge routes
dispatched requests to these functions on the main thread.

Coordinate outputs are converted from Fusion's internal centimeters to
millimeters for user-friendly display (multiply by 10 for length, 100 for area).
"""
import os
import tempfile
import uuid

import adsk.core
import adsk.fusion


def _iter_collection(collection):
    for i in range(collection.count):
        yield collection.item(i)


def get_design_state(design: adsk.fusion.Design) -> dict:
    """Return comprehensive design state for agent context.

    Provides the agent with full awareness of the current workspace: document
    metadata, all bodies with geometry counts, all sketches with profile counts,
    all components, and timeline length.

    Args:
        design: The active Fusion Design object.

    Returns:
        Dict with keys:
            document_name (str): Name of the active document.
            design_type (str): 'parametric' or 'direct'.
            root_component (str): Name of the root component.
            units (str): Default length units (e.g. 'mm', 'cm', 'in').
            body_count (int): Number of bodies in the root component.
            bodies (list): List of body dicts with name, index, face_count,
                edge_count, volume_cm3, is_visible.
            sketch_count (int): Number of sketches in the root component.
            sketches (list): List of sketch dicts with name, index, profile_count.
            component_count (int): Total components including root.
            components (list): List of component dicts with name, body_count,
                sketch_count.
            timeline_count (int): Number of timeline items.
    """
    root = design.rootComponent
    timeline = design.timeline

    bodies = []
    for i, body in enumerate(_iter_collection(root.bRepBodies)):
        bodies.append({
            'name': body.name,
            'index': i,
            'face_count': body.faces.count,
            'edge_count': body.edges.count,
            'volume_cm3': body.volume,
            'is_visible': body.isVisible,
        })

    sketches = []
    for i, sk in enumerate(_iter_collection(root.sketches)):
        sketches.append({
            'name': sk.name,
            'index': i,
            'profile_count': sk.profiles.count,
        })

    components = []
    for i, occ in enumerate(_iter_collection(root.allOccurrences)):
        comp = occ.component
        transform = occ.transform
        comp_bodies = []
        for j, b in enumerate(_iter_collection(comp.bRepBodies)):
            comp_bodies.append({'name': b.name, 'index': j})
        comp_sketches = []
        for j, s in enumerate(_iter_collection(comp.sketches)):
            comp_sketches.append({'name': s.name, 'index': j})
        components.append({
            'name': comp.name,
            'body_count': comp.bRepBodies.count,
            'sketch_count': comp.sketches.count,
            'bodies': comp_bodies,
            'sketches': comp_sketches,
            'transform': {
                'translation': [
                    round(transform.translation.x * 10, 2),
                    round(transform.translation.y * 10, 2),
                    round(transform.translation.z * 10, 2),
                ]
            },
        })

    return {
        'document_name': design.parentDocument.name,
        'design_type': 'parametric' if design.designType == 1 else 'direct',
        'root_component': root.name,
        'units': design.unitsManager.defaultLengthUnits,
        'active_component': design.activeComponent.name,
        'body_count': root.bRepBodies.count,
        'bodies': bodies,
        'sketch_count': root.sketches.count,
        'sketches': sketches,
        'component_count': root.allOccurrences.count + 1,
        'components': components,
        'timeline_count': timeline.count,
    }


def get_body_edges(design: adsk.fusion.Design, body_name: str) -> dict:
    """List all edges of a body with positional metadata for AI identification.

    The agent cannot visually select edges, so this provides geometric data
    (start, end, midpoint coordinates in mm, length, linearity) that the agent
    uses to identify the correct edges for fillet, chamfer, and other operations.

    Args:
        design: The active Fusion Design object.
        body_name: Name of the body in the active component.

    Returns:
        Dict with keys:
            body_name (str): Name of the body.
            edge_count (int): Total number of edges.
            edges (list): List of edge dicts with index, start [x,y,z] in mm,
                end [x,y,z] in mm, midpoint [x,y,z] in mm, length_mm (float),
                is_linear (bool).
    """
    comp = design.activeComponent
    body = comp.bRepBodies.itemByName(body_name)
    if body is None:
        available = [body.name for body in _iter_collection(comp.bRepBodies)]
        raise ValueError(
            f"No body named '{body_name}' in active component '{comp.name}'. "
            f"Available: {available}"
        )
    edges = []

    for i, edge in enumerate(_iter_collection(body.edges)):
        evaluator = edge.evaluator

        # Get start and end points
        success, start_pt, end_pt = evaluator.getEndPoints()
        if not success:
            continue

        # Get midpoint at parametric center
        param_range = evaluator.parametricRange()
        mid_param = (param_range.minValue + param_range.maxValue) / 2
        success_mid, mid_pt = evaluator.getPointAtParameter(mid_param)

        midpoint = [0.0, 0.0, 0.0]
        if success_mid:
            midpoint = [
                round(mid_pt.x * 10, 2),
                round(mid_pt.y * 10, 2),
                round(mid_pt.z * 10, 2),
            ]

        # Determine if edge is linear (Line3D has curveType == 0)
        is_linear = edge.geometry.curveType == 0

        edges.append({
            'index': i,
            'start': [
                round(start_pt.x * 10, 2),
                round(start_pt.y * 10, 2),
                round(start_pt.z * 10, 2),
            ],
            'end': [
                round(end_pt.x * 10, 2),
                round(end_pt.y * 10, 2),
                round(end_pt.z * 10, 2),
            ],
            'midpoint': midpoint,
            'length_mm': round(edge.length * 10, 2),
            'is_linear': is_linear,
        })

    return {
        'body_name': body.name,
        'edge_count': len(edges),
        'edges': edges,
    }


def get_body_faces(design: adsk.fusion.Design, body_name: str) -> dict:
    """List all faces of a body with positional metadata for AI identification.

    Provides centroid, area, and planarity for each face so the agent can
    identify target faces for shell, hole, and other face-based operations.

    Args:
        design: The active Fusion Design object.
        body_name: Name of the body in the active component.

    Returns:
        Dict with keys:
            body_name (str): Name of the body.
            face_count (int): Total number of faces.
            faces (list): List of face dicts with index, centroid_mm [x,y,z],
                area_mm2 (float), is_planar (bool).
    """
    comp = design.activeComponent
    body = comp.bRepBodies.itemByName(body_name)
    if body is None:
        available = [body.name for body in _iter_collection(comp.bRepBodies)]
        raise ValueError(
            f"No body named '{body_name}' in active component '{comp.name}'. "
            f"Available: {available}"
        )
    faces = []

    for i, face in enumerate(_iter_collection(body.faces)):
        centroid = face.centroid

        # Determine if face is planar (Plane has surfaceType == 0)
        is_planar = face.geometry.surfaceType == 0

        faces.append({
            'index': i,
            'centroid_mm': [
                round(centroid.x * 10, 2),
                round(centroid.y * 10, 2),
                round(centroid.z * 10, 2),
            ],
            'area_mm2': round(face.area * 100, 2),
            'is_planar': is_planar,
        })

    return {
        'body_name': body.name,
        'face_count': len(faces),
        'faces': faces,
    }


def get_active_selection(app: adsk.core.Application) -> dict:
    """Read the current user selection in Fusion 360.

    Allows the agent to respond to selection-based requests by inspecting
    what the user has selected in the viewport.

    Args:
        app: The Fusion 360 Application object.

    Returns:
        Dict with keys:
            selection_count (int): Number of selected entities.
            selections (list): List of selection dicts with entity_type (str),
                name (str), entity_token (str).
    """
    ui = app.userInterface
    active_sel = ui.activeSelections

    selections = []
    for selection in _iter_collection(active_sel):
        entity = selection.entity

        entity_type = entity.objectType if entity else 'Unknown'
        name = getattr(entity, 'name', '')
        entity_token = ''
        if hasattr(entity, 'entityToken'):
            try:
                entity_token = entity.entityToken
            except Exception:
                entity_token = ''

        selections.append({
            'entity_type': entity_type,
            'name': name,
            'entity_token': entity_token,
        })

    return {
        'selection_count': active_sel.count,
        'selections': selections,
    }


# ======================================================================
# Phase 4: Component management, camera control, and entity search
# ======================================================================


def _component_to_dict(comp, occ=None) -> dict:
    """Serialize a Fusion component to a dict with bodies, sketches, bounding box.

    Args:
        comp: A Fusion Component object.
        occ: Optional Occurrence (for transform data). Omit for root component.

    Returns:
        Dict with component details including bodies, sketches, bounding box,
        and transform (if occurrence provided).
    """
    bbox = comp.boundingBox

    bodies = []
    for i, body in enumerate(_iter_collection(comp.bRepBodies)):
        bodies.append({
            'name': body.name,
            'index': i,
            'face_count': body.faces.count,
            'edge_count': body.edges.count,
        })

    sketches = []
    for i, sk in enumerate(_iter_collection(comp.sketches)):
        sketches.append({
            'name': sk.name,
            'index': i,
            'profile_count': sk.profiles.count,
        })

    result = {
        'name': comp.name,
        'body_count': comp.bRepBodies.count,
        'bodies': bodies,
        'sketch_count': comp.sketches.count,
        'sketches': sketches,
        'bounding_box': {
            'min': [
                round(bbox.minPoint.x * 10, 2),
                round(bbox.minPoint.y * 10, 2),
                round(bbox.minPoint.z * 10, 2),
            ],
            'max': [
                round(bbox.maxPoint.x * 10, 2),
                round(bbox.maxPoint.y * 10, 2),
                round(bbox.maxPoint.z * 10, 2),
            ],
        } if bbox else None,
    }

    if occ:
        transform = occ.transform
        result['transform'] = {
            'translation': [
                round(transform.translation.x * 10, 2),
                round(transform.translation.y * 10, 2),
                round(transform.translation.z * 10, 2),
            ]
        }

    return result


def get_component_details(design: adsk.fusion.Design, name: str) -> dict:
    """Get detailed state for a named component.

    Searches root component first (case-insensitive name match), then all child
    components via occurrences. Returns body/sketch lists, bounding box, and
    transform for non-root components.

    Args:
        design: The active Fusion Design object.
        name: Component name to look up (case-insensitive match).

    Returns:
        Dict with keys: name, body_count, bodies, sketch_count, sketches,
        bounding_box, and transform (for non-root components).

    Raises:
        ValueError: If no component matches the given name.
    """
    root = design.rootComponent

    # Check root component first
    if root.name.lower() == name.lower():
        return _component_to_dict(root)

    # Search child components via occurrences
    for occ in _iter_collection(root.allOccurrences):
        if occ.component.name.lower() == name.lower():
            return _component_to_dict(occ.component, occ)

    raise ValueError(f"Component '{name}' not found in design.")


def create_component(design: adsk.fusion.Design, name: str) -> dict:
    """Create a new component in the design.

    Creates an empty component at the origin (identity transform) and assigns
    the given name. The component is added as a child of the root component.

    Args:
        design: The active Fusion Design object.
        name: Name for the new component.

    Returns:
        Dict with keys: component_name (str), occurrence_index (int).
    """
    root = design.rootComponent
    trans = adsk.core.Matrix3D.create()  # Identity transform (origin)
    occ = root.occurrences.addNewComponent(trans)
    occ.component.name = name

    # Find the occurrence index in allOccurrences
    occurrence_index = -1
    for i, occurrence in enumerate(_iter_collection(root.allOccurrences)):
        if occurrence == occ:
            occurrence_index = i
            break

    return {
        'component_name': occ.component.name,
        'occurrence_index': occurrence_index,
    }


def set_active_component(design: adsk.fusion.Design, name: str) -> dict:
    """Activate a component by name.

    For the root component, calls design.activateRootComponent(). For child
    components, finds the occurrence by name and calls occ.activate().

    CRITICAL: Do NOT set design.activeComponent directly -- it is read-only.

    Args:
        design: The active Fusion Design object.
        name: Name of the component to activate (case-insensitive match).

    Returns:
        Dict with keys: activated (bool), component_name (str).

    Raises:
        ValueError: If no component matches the given name.
    """
    root = design.rootComponent

    # Check if targeting root
    if name.lower() == root.name.lower():
        design.activateRootComponent()
        return {'activated': True, 'component_name': root.name}

    # Find and activate the occurrence
    for occ in _iter_collection(root.allOccurrences):
        if occ.component.name.lower() == name.lower():
            occ.activate()
            return {'activated': True, 'component_name': occ.component.name}

    raise ValueError(f"Component '{name}' not found in design.")


def find_named_entity(design: adsk.fusion.Design, name: str) -> dict:
    """Search design tree for entities matching the given name.

    Performs case-insensitive substring search across: root bodies, root
    sketches, child components (and their bodies/sketches), and joints.

    Args:
        design: The active Fusion Design object.
        name: Entity name to search for (case-insensitive substring match).

    Returns:
        Dict with keys: query (str), match_count (int), matches (list of dicts
        with type, name, component, index).
    """
    name_lower = name.lower()
    matches = []
    root = design.rootComponent

    # Search root component bodies
    for i, body in enumerate(_iter_collection(root.bRepBodies)):
        if name_lower in body.name.lower():
            matches.append({
                'type': 'body',
                'name': body.name,
                'component': root.name,
                'index': i,
            })

    # Search root sketches
    for i, sk in enumerate(_iter_collection(root.sketches)):
        if name_lower in sk.name.lower():
            matches.append({
                'type': 'sketch',
                'name': sk.name,
                'component': root.name,
                'index': i,
            })

    # Search child components and their contents
    for i, occ in enumerate(_iter_collection(root.allOccurrences)):
        comp = occ.component

        # Component name match
        if name_lower in comp.name.lower():
            matches.append({
                'type': 'component',
                'name': comp.name,
                'component': comp.name,
                'index': i,
            })

        # Bodies within component
        for j, body in enumerate(_iter_collection(comp.bRepBodies)):
            if name_lower in body.name.lower():
                matches.append({
                    'type': 'body',
                    'name': body.name,
                    'component': comp.name,
                    'index': j,
                })

        # Sketches within component
        for j, sk in enumerate(_iter_collection(comp.sketches)):
            if name_lower in sk.name.lower():
                matches.append({
                    'type': 'sketch',
                    'name': sk.name,
                    'component': comp.name,
                    'index': j,
                })

    # Search joints
    for i, joint in enumerate(_iter_collection(root.joints)):
        if name_lower in joint.name.lower():
            matches.append({
                'type': 'joint',
                'name': joint.name,
                'component': root.name,
                'index': i,
            })

    return {
        'query': name,
        'match_count': len(matches),
        'matches': matches,
    }


def set_camera_view(app: adsk.core.Application, view_name: str) -> dict:
    """Set viewport camera to a named standard view and capture screenshot.

    Validates the view name against STANDARD_VIEWS config, sets the camera
    orientation, fits the model in view, and captures a screenshot to a temp
    file for use as vision input.

    CRITICAL: Camera must be re-assigned to viewport after modification --
    viewport.camera returns a copy, not a reference.

    Args:
        app: The Fusion 360 Application object.
        view_name: One of: front, back, top, bottom, left, right, iso.

    Returns:
        Dict with keys: view_name (str), screenshot_path (str).

    Raises:
        ValueError: If view_name is not a recognized standard view.
    """
    from ..config import STANDARD_VIEWS, VIEWPORT_CAPTURE_WIDTH, VIEWPORT_CAPTURE_HEIGHT

    view_name_lower = view_name.lower()
    if view_name_lower not in STANDARD_VIEWS:
        raise ValueError(
            f"Unknown view '{view_name}'. "
            f"Valid: {list(STANDARD_VIEWS.keys())}"
        )

    viewport = app.activeViewport
    camera = viewport.camera
    camera.viewOrientation = STANDARD_VIEWS[view_name_lower]
    camera.isFitView = True
    camera.isSmoothTransition = False
    viewport.camera = camera  # CRITICAL: must re-assign to apply

    # Capture screenshot to temp file
    filepath = os.path.join(
        tempfile.gettempdir(),
        f'meltdown_view_{uuid.uuid4().hex[:8]}.png'
    )
    viewport.saveAsImageFile(
        filepath,
        VIEWPORT_CAPTURE_WIDTH,
        VIEWPORT_CAPTURE_HEIGHT,
    )

    return {
        'view_name': view_name,
        'screenshot_path': filepath,
    }


def capture_multi_angle(app: 'adsk.core.Application', params: dict) -> dict:
    """Capture viewport screenshots from multiple standard angles.

    Saves the current camera state, iterates through the requested angles,
    captures a screenshot at each one, then restores the original camera
    so the user's view is not disturbed.

    CRITICAL: Camera must be re-assigned to viewport after modification --
    viewport.camera returns a copy, not a reference.

    Args:
        app: The Fusion 360 Application object.
        params: Dict with keys:
            width (int): Screenshot width in pixels.
            height (int): Screenshot height in pixels.
            angles (list[str]): Angle names from STANDARD_VIEWS (e.g. ['front', 'right', 'top', 'iso']).

    Returns:
        Dict with key 'screenshots': list of {'angle': str, 'filepath': str}.
    """
    from ..config import STANDARD_VIEWS, VIEWPORT_CAPTURE_WIDTH, VIEWPORT_CAPTURE_HEIGHT, VISUAL_REVIEW_ANGLES

    width = params.get('width', VIEWPORT_CAPTURE_WIDTH)
    height = params.get('height', VIEWPORT_CAPTURE_HEIGHT)
    angles = params.get('angles', VISUAL_REVIEW_ANGLES)

    viewport = app.activeViewport
    original_camera = viewport.camera  # Fusion returns a copy -- this IS the save

    screenshots = []
    for angle in angles:
        angle_lower = angle.lower()
        if angle_lower not in STANDARD_VIEWS:
            # Skip unknown angles with a print warning (no futil import in state_ops)
            print(f'[Meltdown] capture_multi_angle: skipping unknown angle "{angle}"')
            continue

        # Set camera to standard view
        camera = viewport.camera
        camera.viewOrientation = STANDARD_VIEWS[angle_lower]
        camera.isFitView = True
        camera.isSmoothTransition = False
        viewport.camera = camera  # CRITICAL: must re-assign to apply

        # Capture screenshot
        filepath = os.path.join(
            tempfile.gettempdir(),
            f'meltdown_review_{angle_lower}_{uuid.uuid4().hex[:8]}.png'
        )
        viewport.saveAsImageFile(filepath, width, height)
        screenshots.append({'angle': angle_lower, 'filepath': filepath})

    # Restore original camera so user's view is not disturbed
    viewport.camera = original_camera

    return {'screenshots': screenshots}


def get_active_selection_detailed(app: adsk.core.Application) -> dict:
    """Read the current user selection with detailed geometry information.

    Enhanced version of get_active_selection that includes bounding boxes,
    edge coordinates, and face centroids/areas for selected entities.

    Args:
        app: The Fusion 360 Application object.

    Returns:
        Dict with keys:
            selection_count (int): Number of selected entities.
            selections (list): List of selection dicts with entity_type, name,
                and conditional geometry: bounding_box_mm, start_mm/end_mm/
                length_mm (edges), centroid_mm/area_mm2 (faces).
    """
    ui = app.userInterface
    active_sel = ui.activeSelections

    selections = []
    for selection in _iter_collection(active_sel):
        entity = selection.entity

        entry = {
            'entity_type': entity.objectType if entity else 'Unknown',
            'name': getattr(entity, 'name', ''),
        }

        # Bounding box (available on bodies, components, etc.)
        bbox = getattr(entity, 'boundingBox', None)
        if bbox is not None:
            try:
                entry['bounding_box_mm'] = {
                    'min': [
                        round(bbox.minPoint.x * 10, 2),
                        round(bbox.minPoint.y * 10, 2),
                        round(bbox.minPoint.z * 10, 2),
                    ],
                    'max': [
                        round(bbox.maxPoint.x * 10, 2),
                        round(bbox.maxPoint.y * 10, 2),
                        round(bbox.maxPoint.z * 10, 2),
                    ],
                }
            except Exception:
                pass

        # Edge geometry (startVertex / endVertex)
        if hasattr(entity, 'startVertex'):
            try:
                start_pt = entity.startVertex.geometry
                end_pt = entity.endVertex.geometry
                entry['start_mm'] = [
                    round(start_pt.x * 10, 2),
                    round(start_pt.y * 10, 2),
                    round(start_pt.z * 10, 2),
                ]
                entry['end_mm'] = [
                    round(end_pt.x * 10, 2),
                    round(end_pt.y * 10, 2),
                    round(end_pt.z * 10, 2),
                ]
                entry['length_mm'] = round(entity.length * 10, 2)
            except Exception:
                pass

        # Face geometry (centroid / area)
        if hasattr(entity, 'centroid'):
            try:
                centroid = entity.centroid
                entry['centroid_mm'] = [
                    round(centroid.x * 10, 2),
                    round(centroid.y * 10, 2),
                    round(centroid.z * 10, 2),
                ]
                entry['area_mm2'] = round(entity.area * 100, 2)
            except Exception:
                pass

        selections.append(entry)

    return {
        'selection_count': active_sel.count,
        'selections': selections,
    }


def get_design_names(design: adsk.fusion.Design) -> dict:
    """Collect all named entities in the design for autocomplete suggestions.

    Lightweight function that returns only names (no geometry data) for use
    in UI autocomplete dropdowns.

    Args:
        design: The active Fusion Design object.

    Returns:
        Dict with keys: components (list of str), bodies (list of str),
        sketches (list of str), joints (list of str). Child component bodies
        and sketches are prefixed with "ComponentName/" for disambiguation.
    """
    root = design.rootComponent

    # Component names
    components = [root.name] + [
        occ.component.name for occ in _iter_collection(root.allOccurrences)
    ]

    # Body names (root bodies unprefixed, child bodies prefixed)
    bodies = [body.name for body in _iter_collection(root.bRepBodies)]
    for occ in _iter_collection(root.allOccurrences):
        comp = occ.component
        bodies.extend(
            f'{comp.name}/{body.name}'
            for body in _iter_collection(comp.bRepBodies)
        )

    # Sketch names (root sketches unprefixed, child sketches prefixed)
    sketches = [sk.name for sk in _iter_collection(root.sketches)]
    for occ in _iter_collection(root.allOccurrences):
        comp = occ.component
        sketches.extend(
            f'{comp.name}/{sk.name}'
            for sk in _iter_collection(comp.sketches)
        )

    # Joint names
    joints = [joint.name for joint in _iter_collection(root.joints)]

    return {
        'components': components,
        'bodies': bodies,
        'sketches': sketches,
        'joints': joints,
    }
