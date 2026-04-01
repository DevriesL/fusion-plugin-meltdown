"""Timeline group management for transaction-based undo.

Main thread only -- never call from worker threads. These functions manage
Fusion 360 timeline groups to enable single-step undo of complete agent
operations.

Per D-08: One complete user request = one transaction group. Compound tools
MUST NOT create their own timeline groups -- only the top-level orchestrator
groups all operations after the agent fully completes.

Per D-09: The start_index is stored when the user request begins and the
group is only created when the agent fully completes. If the user says
"continue" after hitting the iteration cap, the continuation remains part
of the same transaction group.
"""
import adsk.fusion


def get_timeline_position(design: adsk.fusion.Design) -> int:
    """Get the current end-of-timeline index.

    Call this before starting agent operations to record where the timeline
    was. After operations complete, pass this index to create_timeline_group()
    to group everything the agent did.

    Args:
        design: The active Fusion Design object.

    Returns:
        The current timeline count (the index where the next timeline item
        will appear).
    """
    return design.timeline.count


def create_timeline_group(design: adsk.fusion.Design, start_index: int,
                          name: str = 'AI Operation') -> dict:
    """Group timeline items from start_index to current end into one group.

    Call this after all agent operations for a user request are complete.
    The resulting timeline group appears as a single collapsible item that
    can be undone with one Cmd+Z / Ctrl+Z.

    If no new timeline items were created (end < start), returns without
    creating a group.

    Args:
        design: The active Fusion Design object.
        start_index: The timeline index recorded before operations started
            (from get_timeline_position()).
        name: Display name for the timeline group (default 'AI Operation').

    Returns:
        Dict with keys:
            grouped (bool): True if a group was created, False if no items
                to group.
            item_count (int): Number of timeline items in the group.
            group_name (str): Name assigned to the group (empty if not grouped).
    """
    timeline = design.timeline
    end_index = timeline.count - 1

    if end_index < start_index:
        return {
            'grouped': False,
            'item_count': 0,
            'group_name': '',
        }

    group = timeline.timelineGroups.add(start_index, end_index)
    if group:
        group.name = name

    item_count = end_index - start_index + 1
    return {
        'grouped': True,
        'item_count': item_count,
        'group_name': name,
    }
