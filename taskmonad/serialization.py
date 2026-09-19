from __future__ import annotations
import inspect
from pathlib import Path
from typing import Any, Callable, Dict, Union
import yaml  # type: ignore[import-untyped]

from taskmonad.task import Task
from taskmonad.schedule import Schedule


class ActionRegistry:
    """Реестр шагов и действий для создания задач из YAML/JSON."""
    _actions: Dict[str, Callable[..., Any]] = {}

    @classmethod
    def register(cls, name: str):
        def decorator(fn: Callable[..., Any]):
            cls._actions[name] = fn
            return fn
        return decorator

    @classmethod
    def get(cls, name: str) -> Callable[..., Any]:
        if name not in cls._actions:
            raise KeyError(f"Действие '{name}' не зарегистрировано в ActionRegistry.")
        return cls._actions[name]

    @classmethod
    def all(cls) -> Dict[str, Callable[..., Any]]:
        return cls._actions.copy()

    @classmethod
    def clear(cls):
        cls._actions.clear()


action = ActionRegistry.register


def _build_step_callable(step_cfg: Dict[str, Any]) -> Callable[[Any], Any]:
    action_name = step_cfg["action"]
    fn = ActionRegistry.get(action_name)
    params = step_cfg.get("params", {})

    def step_invoker(incoming_val: Any = None):
        if not params:
            sig = inspect.signature(fn)
            return fn(incoming_val) if len(sig.parameters) > 0 else fn()
        try:
            return fn(**params)
        except TypeError:
            return fn(incoming_val, **params)

    step_invoker.__name__ = step_cfg.get("name", action_name)
    return step_invoker


def build_task_from_dict(data: Dict[str, Any]) -> Task[Any]:
    task_name = data.get("name", "TaskFromYaml")
    current_task: Task[Any] = Task(name=task_name)

    if "schedule" in data:
        current_task.schedule_config = Schedule.from_dict(data["schedule"])

    for step_cfg in data.get("pipeline", []):
        stype = step_cfg.get("type", "step")
        step_name = step_cfg.get("name")

        if stype == "step":
            invoker = _build_step_callable(step_cfg)
            current_task = current_task.bind(invoker, step_name=step_name)

        elif stype == "tap":
            invoker = _build_step_callable(step_cfg)
            current_task = current_task.tap(invoker, step_name=step_name)

        elif stype == "parallel":
            branch_tasks = []
            for branch_cfg in step_cfg.get("branches", []):
                fn = ActionRegistry.get(branch_cfg["action"])
                params = branch_cfg.get("params", {})
                b_name = branch_cfg.get("name", f"{branch_cfg['action']}(...)")
                branch_task = fn(**params) if params else fn()
                if isinstance(branch_task, Task):
                    branch_task.name = b_name
                    branch_tasks.append(branch_task)
                else:
                    branch_tasks.append(Task.of(branch_task, name=b_name))

            parallel_node = Task.parallel(*branch_tasks, name=step_name or "ParallelGroup")
            current_task = current_task >> parallel_node

        elif stype == "if_else":
            cond_fn = ActionRegistry.get(step_cfg["condition"])
            then_fn = ActionRegistry.get(step_cfg["then"])
            else_fn = ActionRegistry.get(step_cfg["else"])
            current_task = current_task.if_else(
                predicate=cond_fn,
                then_branch=then_fn,
                else_branch=else_fn,
            )

    hooks = data.get("hooks", {})
    if "on_success" in hooks:
        succ_fn = ActionRegistry.get(hooks["on_success"])
        current_task.success(succ_fn)

    if "on_error" in hooks:
        err_fn = ActionRegistry.get(hooks["on_error"])
        current_task.error(err_fn)

    # Гарантируем сохранение имени задачи из манифеста
    current_task.name = task_name

    return current_task


def build_task_from_yaml(source: Union[str, Path]) -> Task[Any]:
    raw_text: str

    if isinstance(source, Path):
        raw_text = source.read_text(encoding="utf-8")
    elif isinstance(source, str):
        # Если строка многострочная, это сырой YAML, а не путь
        if "\n" in source or "\r" in source:
            raw_text = source
        else:
            try:
                path = Path(source)
                if path.is_file():
                    raw_text = path.read_text(encoding="utf-8")
                else:
                    raw_text = source
            except OSError:
                raw_text = source
    else:
        raw_text = str(source)

    data = yaml.safe_load(raw_text)
    return build_task_from_dict(data)