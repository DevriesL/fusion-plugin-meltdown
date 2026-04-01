"""Chat conversation state management.

Manages two kinds of history:
1. PydanticAI message_history (list[ModelMessage]) -- passed to run_sync() for
   conversation continuity. Includes tool calls, binary content, everything.
2. Display messages (list[dict]) -- simplified {role, text} dicts for rendering
   in the chat UI. Stored separately for efficient palette restoration.

Also manages: message queue (D-16), cancel flag (D-15), agent busy flag.

Thread safety: All mutable state protected by a single lock. The cancel flag
uses threading.Event for efficient cross-thread signaling.
"""
import threading


_lock = threading.Lock()

# PydanticAI conversation history (list of ModelMessage objects)
_conversation_history: list = []

# Display messages for UI rendering (list of {role: 'user'|'assistant', text: str})
_display_messages: list[dict] = []

# Message queue for requests arriving while agent is busy (D-16)
_message_queue: list[str] = []

# Cancel flag -- threading.Event for efficient cross-thread signaling (D-15)
_cancel_flag = threading.Event()

# Agent busy flag -- set when worker thread is processing
_agent_busy = threading.Event()


# ******** Conversation history (PydanticAI message_history) ********

def get_history() -> list:
    """Get copy of PydanticAI message history for passing to run_sync()."""
    with _lock:
        return list(_conversation_history)


def update_history(messages: list):
    """Replace conversation history with result.all_messages() output.

    Args:
        messages: Complete message list from result.all_messages().
                  NEVER truncate or filter -- tool calls must stay paired.
    """
    global _conversation_history
    with _lock:
        _conversation_history = list(messages)


def clear_history():
    """Clear all conversation state. Called by /clear command (D-12)."""
    global _conversation_history, _display_messages, _message_queue
    with _lock:
        _conversation_history = []
        _display_messages = []
        _message_queue = []


# ******** Display messages (for UI rendering) ********

def get_display_messages() -> list[dict]:
    """Get display messages for palette history restoration (D-10)."""
    with _lock:
        return list(_display_messages)


def add_display_message(role: str, text: str):
    """Add a display message. role is 'user' or 'assistant'."""
    with _lock:
        _display_messages.append({'role': role, 'text': text})


def clear_display_messages():
    """Clear display messages only."""
    global _display_messages
    with _lock:
        _display_messages = []


# ******** Message queue (D-16) ********

def enqueue_message(text: str):
    """Queue a user message that arrived while agent is busy."""
    with _lock:
        _message_queue.append(text)


def dequeue_message() -> str | None:
    """Pop the next queued message, or None if queue is empty."""
    with _lock:
        return _message_queue.pop(0) if _message_queue else None


def has_queued() -> bool:
    """Check if there are queued messages."""
    with _lock:
        return len(_message_queue) > 0


# ******** Cancel flag (D-15) ********

def request_cancel():
    """Set the cancel flag. Called when user sends /stop."""
    _cancel_flag.set()


def is_cancelled() -> bool:
    """Check if cancellation was requested."""
    return _cancel_flag.is_set()


def reset_cancel():
    """Clear the cancel flag. Called before starting new agent run."""
    _cancel_flag.clear()


# ******** Agent busy flag ********

def set_agent_busy():
    """Mark agent as busy. Called when worker thread starts."""
    _agent_busy.set()


def is_agent_busy() -> bool:
    """Check if agent is currently processing."""
    return _agent_busy.is_set()


def clear_agent_busy():
    """Mark agent as idle. Called when worker thread finishes."""
    _agent_busy.clear()
