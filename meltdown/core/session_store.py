"""Session persistence: save, load, list, delete, and prune conversation sessions.

Each session is a JSON file in the .sessions/ directory. Files contain:
- version: schema version (currently 1)
- id: UUID hex string
- metadata: created_at, updated_at, preview (first user message truncated)
- display_messages: list of {role, text} dicts for UI rendering
- agent_history: serialized PydanticAI ModelMessage list (BinaryContent stripped)

Atomic writes via tempfile + os.replace prevent corruption on crash (SESS-04).
Auto-prune removes oldest sessions beyond MAX_SESSIONS limit (SESS-05).
"""

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone

from .. import config


def create_session_id() -> str:
    """Generate a new session ID (32-char hex string, no dashes)."""
    return uuid.uuid4().hex


def _ensure_session_dir():
    """Create the session directory if it doesn't exist (idempotent)."""
    os.makedirs(config.SESSION_DIR, exist_ok=True)


def _strip_binary_content(messages: list) -> list:
    """Deep-strip BinaryContent from PydanticAI ModelMessage list for compact storage.

    Replaces BinaryContent items with a placeholder string so the AI
    knows an image was present but doesn't get stale visual data.

    On any error, returns the original messages unchanged (graceful degradation).
    """
    try:
        from pydantic_ai.messages import ModelRequest, UserPromptPart, BinaryContent

        cleaned = []
        for msg in messages:
            if hasattr(msg, 'parts'):
                new_parts = []
                for part in msg.parts:
                    if isinstance(part, UserPromptPart) and isinstance(part.content, list):
                        # UserPromptPart can contain mixed text + BinaryContent
                        new_content = []
                        for item in part.content:
                            if isinstance(item, BinaryContent):
                                new_content.append('[Viewport screenshot was here]')
                            else:
                                new_content.append(item)
                        new_parts.append(UserPromptPart(content=new_content))
                    else:
                        new_parts.append(part)
                # Reconstruct message with cleaned parts
                cleaned.append(type(msg)(parts=new_parts))
            else:
                cleaned.append(msg)
        return cleaned
    except Exception:
        return messages


def _get_preview(display_messages: list) -> str:
    """Return first user message text truncated to 80 chars for session card preview.

    Args:
        display_messages: List of {role, text} dicts.

    Returns:
        Preview string, or '(empty session)' if no user messages found.
    """
    for msg in display_messages:
        if isinstance(msg, dict) and msg.get('role') == 'user':
            text = msg.get('text', '')
            if text:
                return text[:80]
    return '(empty session)'


def save_session(session_id: str, display_messages: list, agent_history: list,
                 created_at: str = None) -> None:
    """Atomically save a session to disk.

    Args:
        session_id: UUID hex string identifying the session.
        display_messages: List of {role, text} dicts for UI rendering.
        agent_history: PydanticAI ModelMessage list (BinaryContent will be stripped).
        created_at: ISO timestamp for session creation. Auto-generated if None.
    """
    _ensure_session_dir()

    # Strip binary content before serialization to keep files small
    cleaned_history = _strip_binary_content(agent_history)

    # Serialize agent history via PydanticAI's official TypeAdapter
    history_data = None
    try:
        from pydantic_ai.messages import ModelMessagesTypeAdapter
        history_json_bytes = ModelMessagesTypeAdapter.dump_json(cleaned_history)
        history_data = json.loads(history_json_bytes.decode('utf-8'))
    except Exception:
        # If serialization fails, save without agent history and log warning
        try:
            from ..lib import fusionAddInUtils as futil
            futil.log('session_store: Failed to serialize agent history, saving without it')
        except Exception:
            pass  # Logging failure is non-critical

    session_data = {
        'version': 1,
        'id': session_id,
        'metadata': {
            'created_at': created_at or datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'preview': _get_preview(display_messages),
        },
        'display_messages': display_messages,
        'agent_history': history_data,
    }

    filepath = os.path.join(config.SESSION_DIR, f'{session_id}.json')
    data_bytes = json.dumps(session_data, indent=2).encode('utf-8')

    # Atomic write: temp file in same directory + os.replace (SESS-04)
    fd, tmp_path = tempfile.mkstemp(dir=config.SESSION_DIR, suffix='.tmp')
    try:
        os.write(fd, data_bytes)
        os.close(fd)
        fd = None  # Mark as closed
        os.replace(tmp_path, filepath)
    except Exception:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    # Auto-prune after successful write (SESS-05)
    prune_sessions()


def load_session(session_id: str) -> dict | None:
    """Load a session from disk by ID.

    Args:
        session_id: UUID hex string identifying the session.

    Returns:
        Parsed session dict, or None on any error (file not found, corrupt, etc.).
        Does NOT deserialize agent_history back to ModelMessage objects --
        that's the caller's responsibility (so deserialization errors are
        handled at the call site per D-07).
    """
    _ensure_session_dir()
    filepath = os.path.join(config.SESSION_DIR, f'{session_id}.json')
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.loads(f.read())
    except (FileNotFoundError, json.JSONDecodeError, IOError, OSError):
        return None


def list_sessions() -> list[dict]:
    """List all sessions sorted by most recent activity (D-13).

    Returns:
        List of session summary dicts with keys: id, updated_at, preview, created_at.
        Corrupted or malformed files are silently skipped.
    """
    _ensure_session_dir()
    sessions = []
    try:
        entries = os.listdir(config.SESSION_DIR)
    except OSError:
        return sessions

    for filename in entries:
        if not filename.endswith('.json'):
            continue
        filepath = os.path.join(config.SESSION_DIR, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.loads(f.read())
            sessions.append({
                'id': data['id'],
                'updated_at': data['metadata']['updated_at'],
                'preview': data['metadata']['preview'],
                'created_at': data['metadata'].get('created_at', ''),
            })
        except (json.JSONDecodeError, KeyError, IOError, OSError):
            continue  # Skip corrupted/malformed files silently

    # Sort by most recent activity first (D-13)
    sessions.sort(key=lambda s: s['updated_at'], reverse=True)
    return sessions


def delete_session(session_id: str) -> bool:
    """Delete a session file from disk.

    Args:
        session_id: UUID hex string identifying the session.

    Returns:
        True if deleted, False if file not found or deletion failed.
    """
    filepath = os.path.join(config.SESSION_DIR, f'{session_id}.json')
    try:
        os.unlink(filepath)
        return True
    except (FileNotFoundError, OSError):
        return False


def prune_sessions() -> int:
    """Remove oldest sessions beyond MAX_SESSIONS limit (SESS-05).

    Called automatically after every save_session(). Deletes the oldest
    sessions (by updated_at) when the total count exceeds config.MAX_SESSIONS.

    Returns:
        Number of sessions pruned.
    """
    sessions = list_sessions()
    if len(sessions) <= config.MAX_SESSIONS:
        return 0

    # Sessions are sorted most-recent-first; prune from the end
    to_prune = sessions[config.MAX_SESSIONS:]
    pruned = 0
    for session in to_prune:
        if delete_session(session['id']):
            pruned += 1
    return pruned
