"""Task and state serialization utilities."""

import json
from typing import Any, Dict


def serialize_state(state: Dict[str, Any]) -> str:
    """Serialize task state to a JSON string."""
    return json.dumps(state)


def deserialize_state(payload: str) -> Dict[str, Any]:
    """Deserialize task state from a JSON string."""
    return json.loads(payload)
