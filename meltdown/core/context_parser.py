"""@reference parsing and resolution for chat messages.

Parses @selection, @component("name"), @view("name"), and @object-name
references from user text, resolves each against Fusion state via bridge
dispatch, and returns structured context for injection into the agent prompt.

Called from worker thread (chatShow entry.py) before agent invocation (D-01).
All Fusion state resolution goes through dispatch_to_main_thread.
"""
import re


# Regex patterns for @references.
# CRITICAL ordering: process reserved keywords (@selection, @component, @view)
# BEFORE the generic @object-name pattern to avoid collision (Research Pitfall 6).
_RE_SELECTION = re.compile(r'@selection\b')
_RE_COMPONENT = re.compile(r'@component\("([^"]+)"\)')
_RE_VIEW = re.compile(r'@view\("([^"]+)"\)')
# Generic @object-name: matches @word but NOT @selection, @component, @view
# Applied AFTER stripping reserved refs from text to avoid collision
_RE_OBJECT = re.compile(r'@(\w+)')
_RESERVED_KEYWORDS = {'selection', 'component', 'view'}


def resolve_references(text: str) -> dict:
    """Parse @references from text and resolve against Fusion state.

    Args:
        text: Raw user message text potentially containing @references.

    Returns:
        Dict with keys:
            cleaned_text (str): Original text preserved for agent (not stripped).
            context_preamble (str): Structured context to prepend to agent prompt.
                Empty string if no @references found or all failed.
            image_path (str|None): Screenshot path if @view was used.
            errors (list[str]): Error messages for failed resolutions.
    """
    from .bridge import dispatch_to_main_thread

    context_parts = []
    errors = []
    image_path = None

    # 1. @selection (D-02)
    if _RE_SELECTION.search(text):
        try:
            result = dispatch_to_main_thread('get_active_selection_detailed')
            if result.get('error'):
                errors.append(f"@selection: {result.get('error_message', 'Failed')}")
            elif result['selection_count'] == 0:
                context_parts.append(
                    'USER SELECTION: Nothing is currently selected in the viewport. '
                    'Ask the user to select geometry first, or use get_design_state to find entities.'
                )
            else:
                context_parts.append(f"USER SELECTION ({result['selection_count']} items):")
                for sel in result['selections']:
                    line = f"  - {sel['entity_type']}"
                    if sel.get('name'):
                        line += f" '{sel['name']}'"
                    if sel.get('bounding_box_mm'):
                        bb = sel['bounding_box_mm']
                        line += f" bbox=[{bb['min']}, {bb['max']}]mm"
                    if sel.get('length_mm'):
                        line += f" length={sel['length_mm']}mm"
                    if sel.get('area_mm2'):
                        line += f" area={sel['area_mm2']}mm2"
                    context_parts.append(line)
        except Exception as e:
            errors.append(f"@selection: {e}")

    # 2. @component("name") (D-03)
    for match in _RE_COMPONENT.finditer(text):
        comp_name = match.group(1)
        try:
            result = dispatch_to_main_thread('get_component_details', {'name': comp_name})
            if result.get('error'):
                errors.append(f"@component(\"{comp_name}\"): {result.get('error_message', 'Not found')}")
            else:
                bbox_str = ''
                if result.get('bounding_box'):
                    bb = result['bounding_box']
                    bbox_str = f" bbox=[{bb['min']}, {bb['max']}]mm"
                body_names = ', '.join(b['name'] for b in result.get('bodies', []))
                context_parts.append(
                    f"COMPONENT '{result['name']}': "
                    f"{result['body_count']} bodies ({body_names}), "
                    f"{result['sketch_count']} sketches{bbox_str}"
                )
        except Exception as e:
            errors.append(f"@component(\"{comp_name}\"): {e}")

    # 3. @view("name") -- sets camera AND captures screenshot (D-04)
    for match in _RE_VIEW.finditer(text):
        view_name = match.group(1)
        try:
            result = dispatch_to_main_thread('set_camera_view', {'view_name': view_name})
            if result.get('error'):
                errors.append(f"@view(\"{view_name}\"): {result.get('error_message', 'Failed')}")
            else:
                image_path = result.get('screenshot_path')
                context_parts.append(f"CAMERA: Set to {view_name} view. Screenshot captured for your visual reference.")
        except Exception as e:
            errors.append(f"@view(\"{view_name}\"): {e}")

    # 4. @object-name -- generic named entity search (D-05)
    # Strip reserved @references from text first to avoid collision (Research Pitfall 6)
    stripped = _RE_SELECTION.sub('', text)
    stripped = _RE_COMPONENT.sub('', stripped)
    stripped = _RE_VIEW.sub('', stripped)

    for match in _RE_OBJECT.finditer(stripped):
        entity_name = match.group(1)
        if entity_name.lower() in _RESERVED_KEYWORDS:
            continue  # Safety check
        try:
            result = dispatch_to_main_thread('find_named_entity', {'name': entity_name})
            if result.get('error'):
                errors.append(f"@{entity_name}: {result.get('error_message', 'Failed')}")
            elif result['match_count'] == 0:
                errors.append(f"@{entity_name}: No matching entity found in design tree.")
            elif result['match_count'] == 1:
                m = result['matches'][0]
                context_parts.append(
                    f"ENTITY @{entity_name}: {m['type']} '{m['name']}' in component '{m.get('component', 'root')}'"
                )
            else:
                # Ambiguous -- list all matches so agent can clarify (D-05)
                context_parts.append(f"ENTITY @{entity_name}: {result['match_count']} matches found:")
                for m in result['matches']:
                    context_parts.append(
                        f"  - {m['type']} '{m['name']}' in '{m.get('component', 'root')}'"
                    )
                context_parts.append('  (Multiple matches -- ask user to clarify which one)')
        except Exception as e:
            errors.append(f"@{entity_name}: {e}")

    # Build preamble
    preamble = ''
    if context_parts:
        preamble = '--- CONTEXT FROM @REFERENCES ---\n' + '\n'.join(context_parts) + '\n--- END CONTEXT ---'
    if errors:
        preamble += '\n\nReference resolution warnings:\n' + '\n'.join(f'  - {e}' for e in errors)

    return {
        'cleaned_text': text,  # Keep original text for agent (per D-01)
        'context_preamble': preamble,
        'image_path': image_path,
        'errors': errors,
    }


def has_references(text: str) -> bool:
    """Quick check if text contains any @references.

    Use this to skip resolution when no @references are present (optimization).
    """
    return bool(
        _RE_SELECTION.search(text) or
        _RE_COMPONENT.search(text) or
        _RE_VIEW.search(text) or
        _RE_OBJECT.search(text)
    )
