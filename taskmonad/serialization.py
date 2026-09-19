from __future__ import annotations
from typing import Any, Callable, Dict
from taskmonad.task import Task
from taskmonad.schedule import Schedule

class ActionRegistry:
    _registry: Dict[str, Callable[..., Task]] = {}

    @classmethod
    def register(cls, name: str):
        def decorator(fn: Callable[..., Task]):
            cls._registry[name] = fn
            return fn
        return decorator

    @classmethod
    def get(cls, name: str) -> Callable[..., Task]:
        if name not in cls._registry:
            raise KeyError(f"Действие '{name}' не найдено в ActionRegistry.")
        return cls._registry[name]

action = ActionRegistry.register