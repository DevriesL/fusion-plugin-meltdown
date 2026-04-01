"""Tool call instrumentation for real-time event dispatch.

Provides InstrumentedToolset -- a WrapperToolset subclass that intercepts
every agent tool call and dispatches tool_call_start / tool_call_end events
to the chat palette via the main-thread bridge.

Architecture:
- InstrumentedToolset wraps the agent's function toolset
- call_tool override dispatches events before and after each tool execution
- Events are dispatched via dispatch_to_main_thread('send_to_palette', ...)
  because the WrapperToolset runs on the worker thread (Research Pitfall 3)
- call_tool is async def per WrapperToolset contract; PydanticAI's run_sync
  handles the event loop internally (Research Pitfall 2)
- No `import adsk` at module level (Research Pitfall 5)
"""
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any

from pydantic_ai.toolsets.wrapper import WrapperToolset
from pydantic_ai.toolsets.abstract import ToolsetTool
from pydantic_ai._run_context import RunContext


def _safe_serialize(obj, max_len=2048):
    """Serialize an object to a JSON string, with fallback and truncation.

    Attempts json.dumps first; on TypeError, falls back to str().
    Truncates result beyond max_len characters and appends '[truncated]'.

    Args:
        obj: The object to serialize.
        max_len: Maximum character length before truncation.

    Returns:
        The serialized string representation.
    """
    try:
        result = json.dumps(obj)
    except (TypeError, ValueError):
        result = str(obj)
    if len(result) > max_len:
        result = result[:max_len] + '[truncated]'
    return result


@dataclass
class InstrumentedToolset(WrapperToolset):
    """Wraps agent tools to dispatch real-time events to the chat palette.

    Intercepts every tool call and dispatches:
    - tool_call_start: before execution (call_id, tool_name, args)
    - tool_call_end: after execution (call_id, tool_name, status,
      result/error, duration)

    Fields:
        dispatch_fn: Callable that sends events to the palette.
                     Signature: dispatch_fn(action: str, data: dict)
    """
    dispatch_fn: Any = None

    async def call_tool(
        self, name: str, tool_args: dict[str, Any],
        ctx: RunContext, tool: ToolsetTool
    ) -> Any:
        """Intercept tool call with before/after event dispatch.

        Generates a unique call_id, measures duration with time.monotonic(),
        and dispatches start/end events through dispatch_fn.
        """
        call_id = uuid.uuid4().hex[:8]
        start = time.monotonic()

        if self.dispatch_fn:
            self.dispatch_fn('tool_call_start', {
                'call_id': call_id,
                'tool_name': name,
                'args': _safe_serialize(tool_args),
            })

        try:
            from .debug_log import dispatch_log
            dispatch_log(f'Tool call: {name}({_safe_serialize(tool_args, max_len=200)})', level='DEBUG', source='tool')
        except Exception:
            pass

        try:
            result = await super().call_tool(name, tool_args, ctx, tool)
            duration = round(time.monotonic() - start, 2)

            if self.dispatch_fn:
                self.dispatch_fn('tool_call_end', {
                    'call_id': call_id,
                    'tool_name': name,
                    'status': 'success',
                    'result': _safe_serialize(result),
                    'duration': duration,
                })
            return result

        except Exception as e:
            duration = round(time.monotonic() - start, 2)
            try:
                from .debug_log import dispatch_log
                dispatch_log(f'Tool error: {name}: {e}', level='ERROR', source='tool')
            except Exception:
                pass
            if self.dispatch_fn:
                self.dispatch_fn('tool_call_end', {
                    'call_id': call_id,
                    'tool_name': name,
                    'status': 'error',
                    'error': str(e),
                    'error_type': type(e).__name__,
                    'duration': duration,
                })
            raise


def create_dispatch_fn(bridge_dispatch):
    """Create a dispatch function for InstrumentedToolset.

    Returns a closure that routes tool events to the palette via the
    main-thread bridge dispatch function.

    Args:
        bridge_dispatch: The dispatch_to_main_thread function from bridge.py.

    Returns:
        A callable with signature dispatch(action: str, data: dict) that
        sends events via bridge_dispatch('send_to_palette', {...}).
    """
    def dispatch(action, data):
        bridge_dispatch('send_to_palette', {'action': action, **data})
    return dispatch
