"""Demonstration of creating and running a TaskMonad pipeline."""

from taskmonad.task import Task


def main() -> None:
    task = (
        Task(lambda: 10)
        .map(lambda x: x * 2)
        .map(lambda x: f"Result: {x}")
    )
    print(task.run())


if __name__ == "__main__":
    main()
