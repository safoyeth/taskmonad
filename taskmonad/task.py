"""Task and Monadic computation abstractions."""

from typing import Any, Callable, Generic, TypeVar

T = TypeVar("T")
U = TypeVar("U")


class Task(Generic[T]):
    """Represents a monadic unit of work or pipeline step."""

    def __init__(self, run_fn: Callable[..., T]) -> None:
        self.run_fn = run_fn

    def map(self, fn: Callable[[T], U]) -> "Task[U]":
        return Task(lambda *args, **kwargs: fn(self.run_fn(*args, **kwargs)))

    def bind(self, fn: Callable[[T], "Task[U]"]) -> "Task[U]":
        return Task(lambda *args, **kwargs: fn(self.run_fn(*args, **kwargs)).run(*args, **kwargs))

    def run(self, *args: Any, **kwargs: Any) -> T:
        return self.run_fn(*args, **kwargs)
