"""Execution context management for TaskMonad."""

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class TaskContext:
    """Execution context carrying shared state and environment."""
    data: Dict[str, Any] = field(default_factory=dict)
