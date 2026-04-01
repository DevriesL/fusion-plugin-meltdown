"""Review and narration toolset."""

from pathlib import Path

from pydantic_ai import BinaryContent, FunctionToolset, RunContext

from ..agent_helpers import FusionDeps, _check_bridge_result

review_toolset = FunctionToolset()


@review_toolset.tool
def visual_review(ctx: RunContext[FusionDeps]) -> list:
    """Capture multi-angle viewport screenshots and review your work visually.

    Captures 4 standard views (front, right, top, iso) to give you
    comprehensive spatial understanding of the current model state.
    Call this after complex multi-step operations or when you are unsure
    about the result. For simple, confident operations (e.g., single
    extrude with known dimensions), you can skip this.
    Returns labeled screenshots from multiple angles for your visual analysis.
    """
    from .. import settings
    from ..bridge import dispatch_to_main_thread

    max_iterations = settings.get('max_visual_iterations')

    # Check iteration cap BEFORE capturing (per D-06, VISL-03)
    if ctx.deps.iteration_count >= max_iterations:
        # Ask user for permission to continue via Fusion message box
        cap_result = dispatch_to_main_thread('show_message_box', {
            'title': 'Meltdown: Iteration Cap',
            'message': (
                f'The agent has performed {ctx.deps.iteration_count} '
                f'visual review iterations.\n\n'
                f'Click OK to allow {max_iterations} more '
                f'iterations,\nor Cancel to stop the agent now.'
            ),
        })
        _check_bridge_result(cap_result, 'show_message_box')
        if cap_result.get('result') == 'cancel':
            return (
                f"Visual review iteration cap ({max_iterations}) "
                "reached. The user chose to stop. Present your current work "
                "as the final result."
            )
        # User clicked OK -- reset counter to allow more iterations (per D-09)
        ctx.deps.iteration_count = 0

    result = dispatch_to_main_thread('capture_multi_angle', {
        'width': settings.get('viewport_capture_width'),
        'height': settings.get('viewport_capture_height'),
        'angles': settings.get('visual_review_angles'),
    })
    _check_bridge_result(result, 'visual_review')

    ctx.deps.iteration_count += 1
    screenshots = result.get('screenshots', [])

    response_parts = [
        f"Multi-angle screenshots captured (iteration {ctx.deps.iteration_count}/"
        f"{max_iterations}). "
        f"Showing {len(screenshots)} views: {', '.join(s['angle'] for s in screenshots)}. "
        "Analyze ALL angles to verify the 3D geometry matches the user's request. "
        "Front and right views reveal profile accuracy, top view shows plan layout, "
        "iso view confirms overall 3D form. "
        "If correct, present the result. If not, continue modifying.",
    ]

    for shot in screenshots:
        image_data = Path(shot['filepath']).read_bytes()
        response_parts.append(f"[{shot['angle']} view]")
        response_parts.append(
            BinaryContent(data=image_data, media_type='image/png')
        )

    return response_parts


@review_toolset.tool
def narrate(message: str) -> str:
    """Send a status message to the user describing what you are doing,
    what failed, or what you are trying next. The user sees this in
    real-time in the chat window.

    Args:
        message: The status message to display.
    """
    from ...lib.fusionAddInUtils.general_utils import log
    from ..bridge import dispatch_to_main_thread

    log(f'Meltdown Agent: {message}')
    dispatch_to_main_thread('send_to_palette', {
        'action': 'narration',
        'text': message,
    })
    return f"Narrated: {message}"
