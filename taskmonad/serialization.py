from __future__ import annotations
import inspect
from pathlib import Path
import re
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import yaml  # type: ignore[import-untyped]

from taskmonad.context import TaskContext
from taskmonad.task import Task, _resolve_val
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
        if not isinstance(name, str):
            raise TypeError(f"Имя действия должно быть строкой, получено: {type(name).__name__}")
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


def _get_by_path(obj: Any, path: str, default: Any = "<Нет данных>") -> Any:
    """Извлекает значение по пути аттрибута/ключа словаря. Если значение отсутствует, возвращает default."""
    if obj is None:
        return default
    curr = obj
    for part in path.split("."):
        if not part:
            continue
        if isinstance(curr, dict):
            if part in curr:
                curr = curr[part]
            else:
                return default
        elif hasattr(curr, part):
            curr = getattr(curr, part)
        else:
            return default
    return curr if curr is not None else default


_EXACT_FIELD_RE = re.compile(
    r"^\s*(?:\{\{\s*(?:input|result|prev)\s*\}\}\.([a-zA-Z0-9_\.]+)|"
    r"\{\{\s*(?:input|result|prev)\.([a-zA-Z0-9_\.]+)\s*\}\}|"
    r"\{\s*(?:input|result|prev)\s*\}\.([a-zA-Z0-9_\.]+)|"
    r"\{\s*(?:input|result|prev)\.([a-zA-Z0-9_\.]+)\s*\})\s*$"
)

_SUB_FIELD_RE = re.compile(
    r"\{\{\s*(?:input|result|prev)\s*\}\}\.([a-zA-Z0-9_\.]+)|"
    r"\{\{\s*(?:input|result|prev)\.([a-zA-Z0-9_\.]+)\s*\}\}|"
    r"\{\s*(?:input|result|prev)\s*\}\.([a-zA-Z0-9_\.]+)|"
    r"\{\s*(?:input|result|prev)\.([a-zA-Z0-9_\.]+)\s*\}"
)


def _build_step_callable(step_cfg: Dict[str, Any]) -> Callable[[Any], Any]:
    action_name = step_cfg["action"]
    fn = ActionRegistry.get(action_name)
    params = step_cfg.get("params", {})
    input_param_name = step_cfg.get("input_param") or step_cfg.get("input_key")

    def step_invoker(incoming_val: Any = None):
        sig = inspect.signature(fn)
        resolved_params = dict(params) if params else {}

        # 1. Интерполяция плейсхолдеров из предыдущего шага пайплайна
        placeholder_tokens = ("{{input}}", "{{result}}", "{{prev}}", "$input", "{input}", "{result}", "{prev}")
        has_placeholder = False

        for k, v in list(resolved_params.items()):
            if isinstance(v, str):
                # А. Проверяем точное совпадение с {{input}}.field или {{input.field}}
                exact_field_m = _EXACT_FIELD_RE.match(v)
                if exact_field_m:
                    field_name = next(g for g in exact_field_m.groups() if g is not None)
                    resolved_params[k] = _get_by_path(incoming_val, field_name, "<Нет данных>")
                    has_placeholder = True
                    continue

                # Б. Точное совпадение с полным {{input}}
                exact_matched = False
                for ph in placeholder_tokens:
                    if v == ph:
                        resolved_params[k] = incoming_val
                        has_placeholder = True
                        exact_matched = True
                        break
                if exact_matched:
                    continue

                # В. Вхождение выражений вида {{input}}.field в подстроку
                cur_str = v
                def _replace_field_match(m: re.Match) -> str:
                    nonlocal has_placeholder
                    has_placeholder = True
                    f_name = next(g for g in m.groups() if g is not None)
                    val = _get_by_path(incoming_val, f_name, "<Нет данных>")
                    return str(val if val is not None else "<Нет данных>")

                if _SUB_FIELD_RE.search(cur_str):
                    cur_str = _SUB_FIELD_RE.sub(_replace_field_match, cur_str)

                # Г. Вхождение полных плейсхолдеров в подстроку
                for ph in placeholder_tokens:
                    if ph in cur_str:
                        cur_str = cur_str.replace(ph, str(incoming_val if incoming_val is not None else ""))
                        has_placeholder = True

                # Д. Прямая подстановка полей словаря вида {field} или {{field}}
                if isinstance(incoming_val, dict):
                    for dk, dv in incoming_val.items():
                        toks = (f"{{{dk}}}", f"{{{{{dk}}}}}")
                        for tok in toks:
                            if tok in cur_str:
                                cur_str = cur_str.replace(tok, str(dv if dv is not None else ""))
                                has_placeholder = True

                resolved_params[k] = cur_str

        # 2. Если incoming_val передан, но в явном виде через плейсхолдеры не привязан
        if incoming_val is not None and not has_placeholder:
            # А. Явно указано имя входного параметра в конфигурации шага
            if input_param_name and input_param_name in sig.parameters:
                resolved_params[input_param_name] = incoming_val
            else:
                # Б. Ищем характерные имена параметров для передачи пайплайн-данных
                pipeline_names = (
                    "incoming_data", "incoming_val", "input_data", "data", "payload",
                    "records", "items", "content", "text", "message", "query", "code"
                )
                target_p = None
                for p_name in pipeline_names:
                    if p_name in sig.parameters:
                        # Если параметр не задан в конфиге или пустой, биндим incoming_val
                        if p_name not in resolved_params or resolved_params[p_name] in ("", None, "—"):
                            target_p = p_name
                            break

                if target_p:
                    resolved_params[target_p] = incoming_val
                elif len(sig.parameters) > 0:
                    # В. Если параметров мало и первый еще не занят в resolved_params
                    first_p = next(iter(sig.parameters.values()))
                    if first_p.name not in resolved_params or resolved_params[first_p.name] in ("", None, "—"):
                        resolved_params[first_p.name] = incoming_val

        # Вызов целевого действия
        if not resolved_params:
            return fn(incoming_val) if (len(sig.parameters) > 0 and incoming_val is not None) else (fn(incoming_val) if len(sig.parameters) > 0 else fn())
        try:
            return fn(**resolved_params)
        except TypeError:
            return fn(incoming_val, **resolved_params)

    step_invoker.__name__ = step_cfg.get("name", action_name)
    return step_invoker


def _resolve_hook_callable(hook_cfg: Union[str, Dict[str, Any]]) -> Callable[..., Any]:
    """Разрешает хук из строки или конфигурации со словарем параметров."""
    if isinstance(hook_cfg, str):
        fn = ActionRegistry.get(hook_cfg)
        return fn
    elif isinstance(hook_cfg, dict):
        act_name = hook_cfg.get("action")
        if not act_name:
            raise ValueError(f"Хук-словарь должен содержать 'action': {hook_cfg}")
        step_invoker = _build_step_callable(hook_cfg)
        def hook_wrapper(res_or_err: Any = None, ctx: Any = None):
            return step_invoker(res_or_err)
        hook_wrapper.__name__ = act_name
        return hook_wrapper
    else:
        raise TypeError(f"Неподдерживаемый тип для хука: {type(hook_cfg).__name__}")


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
            branches = step_cfg.get("branches") or step_cfg.get("steps") or []

            def make_parallel_step(incoming_val: Any, _branches=branches, _s_name=step_name) -> Task[List[Any]]:
                branch_tasks: List[Task[Any]] = []
                for branch_cfg in _branches:
                    act = branch_cfg.get("action")
                    if not act:
                        continue
                    b_name = branch_cfg.get("name", f"{act}(...)")
                    b_invoker = _build_step_callable(branch_cfg)

                    async def branch_comp(ctx: TaskContext, _inv=b_invoker, _in=incoming_val):
                        try:
                            res = _inv(_in)
                            res = await _resolve_val(res)
                            return ctx, res
                        except Exception as e:
                            return ctx, e

                    branch_tasks.append(Task(name=b_name, computation=branch_comp))
                return Task.parallel(*branch_tasks, name=_s_name or "ParallelGroup")

            current_task = current_task.bind(make_parallel_step, step_name=step_name or "ParallelGroup")

        elif stype == "if_else":
            cond_cfg = step_cfg.get("condition")
            if isinstance(cond_cfg, str):
                cond_fn = ActionRegistry.get(cond_cfg)
            else:
                params = step_cfg.get("params", {})
                cond_idx = params.get("cond_type_idx", 0)
                step_check = str(params.get("step_check", "")).lower()

                def cond_fn(x: Any) -> bool:
                    # Режим 1: Проверка результата предыдущего шага
                    if cond_idx == 1 or step_check:
                        if "не пустой" in step_check or "!=" in step_check:
                            return x is not None and x != "" and x != {} and x != []
                        elif "пустой" in step_check or "==" in step_check:
                            return x is None or x == "" or x == {} or x == []
                        elif "успех" in step_check or "success" in step_check:
                            return bool(x) and not isinstance(x, Exception)
                        return bool(x) and not isinstance(x, Exception)

                    # Режим 2: Проверка существования файла
                    if cond_idx == 2 or "file_path" in params:
                        from pathlib import Path
                        fp = params.get("file_path", "")
                        return Path(fp).exists() if fp else False

                    # Режим 0: Сравнение поля объекта/словаря
                    field = params.get("field", "status")
                    op = str(params.get("operator", "=="))
                    val = str(params.get("value", "ok"))
                    target = x
                    if isinstance(x, dict) and field:
                        target = x.get(field, "")
                    s_target = str(target)
                    s_val = val
                    if op in ("==", "равно", "равно (==)"):
                        return s_target == s_val
                    elif op in ("!=", "не", "не равно (!=)"):
                        return s_target != s_val
                    elif op in ("in", "содержит", "содержит (in)"):
                        return s_val in s_target
                    elif op in (">", "больше", "больше (>)"):
                        try:
                            return float(s_target) > float(s_val)
                        except (ValueError, TypeError):
                            return s_target > s_val
                    elif op in ("<", "меньше", "меньше (<)"):
                        try:
                            return float(s_target) < float(s_val)
                        except (ValueError, TypeError):
                            return s_target < s_val
                    return bool(target)

            def _resolve_branch(b_cfg: Any) -> Task[Any]:
                if isinstance(b_cfg, str):
                    fn = ActionRegistry.get(b_cfg)
                    res = fn()
                    return res if isinstance(res, Task) else Task.of(res)
                elif isinstance(b_cfg, list):
                    sub_t: Task[Any] = Task("BranchSubPipeline")
                    for s in b_cfg:
                        if not s.get("action"):
                            continue
                        st = s.get("type", "step")
                        invoker = _build_step_callable(s)
                        if st == "tap":
                            sub_t = sub_t.tap(invoker, step_name=s.get("name"))
                        else:
                            sub_t = sub_t.bind(invoker, step_name=s.get("name"))
                    return sub_t
                elif isinstance(b_cfg, dict):
                    if b_cfg.get("action"):
                        invoker = _build_step_callable(b_cfg)
                        return Task("BranchStep").bind(invoker, step_name=b_cfg.get("name"))
                return Task.of(None)

            then_task = _resolve_branch(step_cfg.get("then", []))
            else_task = _resolve_branch(step_cfg.get("else", []))
            current_task = current_task.if_else(
                predicate=cond_fn,
                then_branch=then_task,
                else_branch=else_task,
            )

    hooks = data.get("hooks", {})
    if "on_success" in hooks and hooks["on_success"]:
        current_task.success(_resolve_hook_callable(hooks["on_success"]))

    if "on_error" in hooks and hooks["on_error"]:
        current_task.error(_resolve_hook_callable(hooks["on_error"]))

    if "on_finally" in hooks and hooks["on_finally"]:
        current_task.always(_resolve_hook_callable(hooks["on_finally"]))

    if "on_always" in hooks and hooks["on_always"]:
        current_task.always(_resolve_hook_callable(hooks["on_always"]))

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