"""Shared helpers for the Fusion modeling agent toolsets."""

from pydantic_ai import ModelRetry


class FusionDeps:
    """Dependencies injected into agent tool functions via RunContext.

    Holds session state for the current agent invocation.
    """

    def __init__(self):
        self.iteration_count = 0  # Visual review iterations in this turn
        self.timeline_start_index = None  # For transaction grouping


def _check_bridge_result(result: dict, operation: str) -> dict:
    """Check bridge result for errors. Raises ModelRetry if error found.

    This enables PydanticAI's built-in retry mechanism: the error message
    is sent back to the LLM so it can adjust parameters and try again.

    Args:
        result: The dict returned by dispatch_to_main_thread.
        operation: Name of the operation, for error context.

    Returns:
        The result dict, unchanged, if no error.

    Raises:
        ModelRetry: If the result contains an error indicator.
    """
    if isinstance(result, dict) and result.get('error'):
        raise ModelRetry(
            f"{operation} failed: {result.get('error_type', 'Unknown')}: "
            f"{result.get('error_message', 'No details')}. "
            f"Try different parameters or check the design state first."
        )
    return result


PROVIDER_PREFIX = {
    'gemini': 'google-gla',
    'claude': 'anthropic',
    'openai': 'openai',
}
