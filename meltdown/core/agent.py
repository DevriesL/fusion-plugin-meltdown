"""PydanticAI agent for Fusion 360 modeling interaction.

Full modeling agent with 27 tool functions grouped into FunctionToolsets under
meltdown.core.tools.

Architecture:
- Model string: built dynamically from settings (ai_provider + ai_model_name)
- Supported providers: Gemini (google-gla), Claude (anthropic), OpenAI (openai)
- API key: read from provider-specific env var (set by secrets.ensure_provider_key)
- Tools use dispatch_to_main_thread() for all Fusion API calls (lazy import)
- agent.run_sync() MUST be called from a worker thread (Research Pitfall 2)
- BinaryContent for passing viewport screenshots to Gemini vision
- ModelRetry for error self-correction via PydanticAI's retry mechanism
- No `import adsk` at module level (Research Pitfall 5)
"""

import os
from pathlib import Path

from pydantic_ai import Agent, BinaryContent

from .agent_helpers import FusionDeps, PROVIDER_PREFIX
from .tools import all_toolsets


def create_agent(toolsets=None) -> Agent:
    """Create and configure the PydanticAI agent with the user-selected model.

    Reads ai_provider and ai_model_name from settings to build the model
    string dynamically. Ensures the correct provider API key env var is set.

    Args:
        toolsets: Optional toolset list override (e.g. instrumented wrappers).
            Defaults to all_toolsets.

    Returns a fully configured Agent instance with all 27 tool functions
    registered.
    """
    from . import settings
    from .secrets import ensure_provider_key

    provider = settings.get('ai_provider', 'gemini')
    model_name = settings.get('ai_model_name', 'gemini-3.1-pro-preview')
    prefix = PROVIDER_PREFIX.get(provider, 'google-gla')
    model_string = f'{prefix}:{model_name}'

    ensure_provider_key(provider)

    return Agent(
        model_string,
        deps_type=FusionDeps,
        toolsets=toolsets or all_toolsets,
        instructions=(
            'You are a Fusion 360 modeling assistant specialized in CNC-machinable '
            'aluminum parts -- enclosures, brackets, plates, mounts, and frames.\n\n'

            'WORKFLOW:\n'
            '1. Call get_design_state to understand what exists\n'
            '2. Plan your modeling steps, then execute\n'
            '3. Use visual_review after complex work to verify\n'
            '4. Narrate what you are doing so the user can follow along\n\n'

            'CONVENTIONS:\n'
            '- Units: all tool parameters are in millimeters\n'
            '- Planes: xy (top), xz (front), yz (side)\n'
            '- Bodies/sketches: reference by name from tool returns or get_design_state\n'
            '- You cannot click geometry -- use get_body_edges/get_body_faces to find '
            'indices by position coordinates\n'
            '- If a tool fails, re-query state (indices may have changed), adjust, retry\n\n'

            'CONTEXT: users may include @references resolved before your turn. '
            '@selection = viewport selection, @component("name") = part details, '
            '@view("front") = camera + screenshot.'
        ),
    )


def run_modeling_agent(prompt: str, image_path: str = None,
                       message_history: list = None) -> tuple:
    """Run the modeling agent with a user prompt and optional reference image.

    MUST be called from a worker thread, not the main thread.
    Manages the full agent turn including transaction grouping and iteration cap.

    Args:
        prompt: The user's natural language modeling request.
        image_path: Optional path to a reference image.
        message_history: Optional list of PydanticAI ModelMessage objects for
            multi-turn conversation continuity (D-11).

    Returns:
        Tuple of (response_text, all_messages) where all_messages is the
        complete conversation history including this turn.
    """
    from .bridge import dispatch_to_main_thread
    from .tool_events import InstrumentedToolset, create_dispatch_fn

    dispatch_fn = create_dispatch_fn(dispatch_to_main_thread)
    instrumented = [
        InstrumentedToolset(wrapped=ts, dispatch_fn=dispatch_fn)
        for ts in all_toolsets
    ]
    agent = create_agent(toolsets=instrumented)
    deps = FusionDeps()

    # Record timeline position for transaction grouping (D-08)
    try:
        timeline_result = dispatch_to_main_thread('get_timeline_position')
        if not timeline_result.get('error'):
            deps.timeline_start_index = timeline_result['position']
    except Exception:
        pass  # No active design yet, will be handled by tools

    # Build prompt with optional image
    user_prompt = [prompt]
    if image_path and os.path.exists(image_path):
        image_data = Path(image_path).read_bytes()
        user_prompt.append(
            BinaryContent(data=image_data, media_type='image/png')
        )

    result = agent.run_sync(
        user_prompt,
        deps=deps,
        message_history=message_history if message_history else None,
    )

    # Create transaction group for undo (D-08)
    if deps.timeline_start_index is not None:
        try:
            dispatch_to_main_thread('create_timeline_group', {
                'start_index': deps.timeline_start_index,
                'name': f'Meltdown: {prompt[:50]}',
            })
        except Exception:
            pass  # Best effort -- group creation failing is non-fatal

    return result.output, result.all_messages()


def run_agent_with_vision(prompt: str, image_path: str = None) -> str:
    """Backward-compatible wrapper. Use run_modeling_agent() for new code.

    Args:
        prompt: The text prompt to send to the agent.
        image_path: Optional path to an image file to include (for vision).

    Returns:
        The agent's text response as a string.
    """
    output, _ = run_modeling_agent(prompt, image_path)
    return output
