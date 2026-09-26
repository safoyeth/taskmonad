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



import re
from taskmonad.context import TaskContext


def _interpolate_value(val: Any, incoming_val: Any = None, ctx_data: Optional[Dict[str, Any]] = None) -> Any:
    if not isinstance(val, str) or ("{" not in val and "$" not in val):
        return val

    scope: Dict[str, Any] = {}
    if ctx_data:
        scope.update(ctx_data)
    if isinstance(incoming_val, dict):
        scope.update(incoming_val)
        scope["result"] = incoming_val
        scope["prev"] = incoming_val
    elif incoming_val is not None:
        scope["result"] = incoming_val
        scope["prev"] = incoming_val

    def replacer(m):
        key = m.group(1).strip()
        parts = key.split(".")
        cur: Any = scope
        for p in parts:
            if isinstance(cur, dict) and p in cur:
                cur = cur[p]
            elif hasattr(cur, p):
                cur = getattr(cur, p)
            else:
                return m.group(0)
        return str(cur)

    res = re.sub(r"\{([a-zA-Z0-9_\.]+)\}", replacer, val)
    res = re.sub(r"\$([a-zA-Z0-9_]+)", lambda m: str(scope.get(m.group(1), m.group(0))), res)
    return res


def _interpolate_params(params: Any, incoming_val: Any = None, ctx_data: Optional[Dict[str, Any]] = None) -> Any:
    if isinstance(params, dict):
        return {k: _interpolate_params(v, incoming_val, ctx_data) for k, v in params.items()}
    elif isinstance(params, list):
        return [_interpolate_params(item, incoming_val, ctx_data) for item in params]
    elif isinstance(params, str):
        return _interpolate_value(params, incoming_val, ctx_data)
    return params


def _build_step_callable(step_cfg: Dict[str, Any]) -> Callable[..., Any]:
    action_name = step_cfg["action"]
    fn = ActionRegistry.get(action_name)
    raw_params = step_cfg.get("params", {})

    def step_invoker(incoming_val: Any = None, ctx: Optional[TaskContext] = None):
        ctx_data = ctx.data if ctx else {}
        resolved_params = _interpolate_params(raw_params, incoming_val, ctx_data)

        sig = inspect.signature(fn)
        call_kwargs = dict(resolved_params) if isinstance(resolved_params, dict) else {}

        # Если кирпичик принимает incoming_val / result / val / data
        for p_name in ("incoming_val", "result", "val", "data"):
            if p_name in sig.parameters and p_name not in call_kwargs and incoming_val is not None:
                call_kwargs[p_name] = incoming_val

        if "ctx" in sig.parameters and "ctx" not in call_kwargs:
            call_kwargs["ctx"] = ctx
        elif "context" in sig.parameters and "context" not in call_kwargs:
            call_kwargs["context"] = ctx

        if not call_kwargs:
            return fn(incoming_val) if len(sig.parameters) > 0 else fn()

        try:
            return fn(**call_kwargs)
        except TypeError:
            try:
                return fn(incoming_val, **call_kwargs)
            except TypeError:
                valid_kw = {k: v for k, v in call_kwargs.items() if k in sig.parameters}
                return fn(**valid_kw)

    step_invoker.__name__ = step_cfg.get("name", action_name)
    return step_invoker



def _resolve_hook_callable(hook_data: Any) -> Optional[Callable[..., Any]]:
    """Разрешает спецификацию хука (str или dict с action) в исполняемый callable."""
    if not hook_data:
        return None
    if isinstance(hook_data, str):
        if hook_data in ActionRegistry._actions:
            return ActionRegistry.get(hook_data)
        return None
    elif isinstance(hook_data, dict) and "action" in hook_data:
        return _build_step_callable(hook_data)
    elif callable(hook_data):
        return hook_data
    return None


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
                act_name = branch_cfg.get("action")
                if not act_name:
                    continue
                fn = ActionRegistry.get(act_name)
                params = branch_cfg.get("params", {})
                b_name = branch_cfg.get("name", f"{act_name}(...)")
                branch_task = fn(**params) if params else fn()
                if isinstance(branch_task, Task):
                    branch_task.name = b_name
                    branch_tasks.append(branch_task)
                else:
                    branch_tasks.append(Task.of(branch_task, name=b_name))

            if branch_tasks:
                parallel_node = Task.parallel(*branch_tasks, name=step_name or "ParallelGroup")
                current_task = current_task >> parallel_node

        elif stype == "if_else":
            p = step_cfg.get("params", {})
            cond_type_idx = int(p.get("cond_type_idx", 0))

            def make_condition(params: Dict[str, Any], action: Optional[str]):
                if action and action in ActionRegistry._actions and action != "system.if_else":
                    base_fn = ActionRegistry.get(action)
                    return lambda x, ctx=None: base_fn(x)

                f = params.get("field", "status")
                op = str(params.get("operator", "==")).strip()
                v = str(params.get("value", "ok")).strip()
                step_check = str(params.get("step_check", "")).strip()
                file_path = str(params.get("file_path", "")).strip()

                def cond_predicate(incoming_val: Any, ctx: Optional[TaskContext] = None) -> bool:
                    ctx_data = ctx.data if ctx else {}
                    if cond_type_idx == 1 or step_check:
                        if "не пустой" in step_check or "not null" in step_check.lower():
                            return incoming_val is not None and incoming_val != "" and incoming_val != [] and incoming_val != {}
                        elif "ok" in step_check.lower() or "успех" in step_check.lower():
                            if isinstance(incoming_val, dict):
                                return str(incoming_val.get("status", "")).lower() == "ok"
                            return str(incoming_val).lower() == "ok"
                        elif "true" in step_check.lower():
                            return bool(incoming_val) and incoming_val is not False and incoming_val != 0
                        return bool(incoming_val)

                    elif cond_type_idx == 2 or file_path:
                        from services.tasks_service.bricks.system_bricks import check_file_exists
                        return check_file_exists(file_path)

                    else:
                        actual_val = ""
                        if isinstance(incoming_val, dict):
                            actual_val = incoming_val.get(f, "")
                        elif ctx_data and f in ctx_data:
                            actual_val = ctx_data[f]
                        elif hasattr(incoming_val, f):
                            actual_val = getattr(incoming_val, f)
                        else:
                            actual_val = incoming_val

                        s_act = str(actual_val)
                        if op in ("==", "равно", "="):
                            return s_act.lower() == v.lower()
                        elif op in ("!=", "не равно"):
                            return s_act.lower() != v.lower()
                        elif op in (">", "больше"):
                            try:
                                return float(s_act) > float(v)
                            except ValueError:
                                return s_act > v
                        elif op in ("<", "меньше"):
                            try:
                                return float(s_act) < float(v)
                            except ValueError:
                                return s_act < v
                        elif op in (">=", "больше или равно"):
                            try:
                                return float(s_act) >= float(v)
                            except ValueError:
                                return s_act >= v
                        elif op in ("<=", "меньше или равно"):
                            try:
                                return float(s_act) <= float(v)
                            except ValueError:
                                return s_act <= v
                        elif op in ("in", "содержит"):
                            return v.lower() in s_act.lower()
                        return bool(actual_val)

                return cond_predicate

            cond_fn = make_condition(p, step_cfg.get("action"))

            def build_branch_task(branch_raw: Any, branch_name: str) -> Callable[[Any], Task[Any]]:
                if isinstance(branch_raw, list):
                    def branch_runner(incoming_val: Any) -> Task[Any]:
                        t = Task.of(incoming_val, name=f"{branch_name}_Start")
                        for s in branch_raw:
                            if isinstance(s, dict) and "action" in s:
                                step_call = _build_step_callable(s)
                                t = t.bind(step_call, step_name=s.get("name") or s.get("action"))
                        return t
                    return branch_runner
                elif isinstance(branch_raw, str) and branch_raw in ActionRegistry._actions:
                    fn = ActionRegistry.get(branch_raw)
                    return lambda val: Task.of(fn(val))
                return lambda val: Task.of(val)

            then_task_factory = build_branch_task(step_cfg.get("then"), "ThenBranch")
            else_task_factory = build_branch_task(step_cfg.get("else"), "ElseBranch")

            current_task = current_task.if_else(
                predicate=cond_fn,
                then_branch=then_task_factory,
                else_branch=else_task_factory,
            )

    hooks = data.get("hooks", {})

    build_hook_callable = _resolve_hook_callable

    if "on_success" in hooks:
        h = build_hook_callable(hooks["on_success"])
        if h:
            current_task.success(h)

    if "on_error" in hooks:
        h = build_hook_callable(hooks["on_error"])
        if h:
            current_task.error(h)

    if "on_finally" in hooks:
        h = build_hook_callable(hooks["on_finally"])
        if h:
            current_task.always(h)

    if "on_always" in hooks:
        h = build_hook_callable(hooks["on_always"])
        if h:
            current_task.always(h)

    current_task.name = task_name
    return current_task


# Гарантируем регистрацию фиктивного system.if_else для чистого соответствия
if "system.if_else" not in ActionRegistry._actions:
    ActionRegistry._actions["system.if_else"] = lambda *a, **k: True


def build_task_from_yaml(source: Union[str, Path]) -> Task[Any]:
    raw_text: str

    if isinstance(source, Path):
        raw_text = source.read_text(encoding="utf-8")
    elif isinstance(source, str):
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