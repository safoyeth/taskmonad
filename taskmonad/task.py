from __future__ import annotations

import asyncio
import inspect
from typing import (
    Any,
    Callable,
    Coroutine,
    Generic,
    List,
    Optional,
    Tuple,
    TypeVar,
    Union,
)

from taskmonad.context import TaskContext
from taskmonad.schedule import Schedule

T = TypeVar("T")
U = TypeVar("U")

Computation = Callable[
    [TaskContext],
    Coroutine[Any, Any, Tuple[TaskContext, Union[T, Exception]]],
]


async def _resolve_val(val: Any) -> Any:
    if inspect.iscoroutine(val):
        return await val
    return val


async def _invoke_hook(hook: Callable[..., Any], result_or_err: Any, ctx: TaskContext) -> Any:
    try:
        sig = inspect.signature(hook)
        param_count = len(sig.parameters)
        if param_count == 0:
            res = hook()
        elif param_count == 1:
            res = hook(result_or_err)
        else:
            res = hook(result_or_err, ctx)
    except (ValueError, TypeError):
        try:
            res = hook(result_or_err, ctx)
        except TypeError:
            try:
                res = hook(result_or_err)
            except TypeError:
                res = hook()
    return await _resolve_val(res)


def _extract_name(target: Any) -> str:
    """Извлекает понятное строковое имя для функции, Task или partial-объекта."""
    if hasattr(target, "name") and target.name:
        return str(target.name)
    if hasattr(target, "func"):  # functools.partial
        return f"{target.func.__name__}(...)"
    if hasattr(target, "__name__"):
        return str(target.__name__)
    return "AnonymousStep"


class SchedulePropertyBridge(Generic[T]):
    def __init__(self, task: Task[T]):
        self._task = task

    @property
    def second(self) -> Task[T]:
        self._task.schedule_config = Schedule().every(1).seconds()
        return self._task

    @property
    def minute(self) -> Task[T]:
        self._task.schedule_config = Schedule().every(1).minutes()
        return self._task

    @property
    def hour(self) -> Task[T]:
        self._task.schedule_config = Schedule().hourly()
        return self._task

    @property
    def day(self) -> Task[T]:
        self._task.schedule_config = Schedule().daily()
        return self._task

    def milliseconds(self, n: Union[int, float]) -> Task[T]:
        self._task.schedule_config = Schedule().every(n).milliseconds()
        return self._task

    def seconds(self, n: Union[int, float]) -> Task[T]:
        self._task.schedule_config = Schedule().every(n).seconds()
        return self._task

    def minutes(self, n: Union[int, float]) -> Task[T]:
        self._task.schedule_config = Schedule().every(n).minutes()
        return self._task

    def hours(self, n: Union[int, float]) -> Task[T]:
        self._task.schedule_config = Schedule().every(n).hours()
        return self._task


class Task(Generic[T]):
    def __init__(
        self,
        name: str = "Task",
        computation: Optional[Computation[T]] = None,
    ):
        self.name = name
        self.schedule_config: Optional[Schedule] = None
        self._success_hooks: List[Callable[..., Any]] = []
        self._error_hooks: List[Callable[..., Any]] = []
        self._finally_hooks: List[Callable[..., Any]] = []

        if computation is None:
            async def default_unit(ctx: TaskContext) -> Tuple[TaskContext, Any]:
                return ctx, None

            self._comp = default_unit
        else:
            async def safe_comp(ctx: TaskContext) -> Tuple[TaskContext, Union[T, Exception]]:
                try:
                    res = await _resolve_val(computation(ctx))
                    if isinstance(res, tuple) and len(res) == 2:
                        return res
                    return ctx, res
                except Exception as e:
                    return ctx, e

            self._comp = safe_comp

    # --- Unit / Return ---
    @classmethod
    def of(cls, value: T, name: str = "Unit") -> Task[T]:
        async def comp(ctx: TaskContext) -> Tuple[TaskContext, Union[T, Exception]]:
            resolved = await _resolve_val(value)
            return ctx, resolved

        return cls(name=name, computation=comp)

    # --- Bind / >>= ---
    def bind(self, fn: Callable[[T], Union[Task[U], U]], step_name: Optional[str] = None) -> Task[U]:
        target_name = step_name or _extract_name(fn)

        async def comp(ctx: TaskContext) -> Tuple[TaskContext, Union[U, Exception]]:
            next_ctx, res = await self._comp(ctx)

            if isinstance(res, Exception):
                return next_ctx, res

            emit_step = next_ctx.get_meta("emit_step")
            if emit_step:
                emit_step(target_name, "running")

            try:
                next_val = fn(res)
                next_task = next_val if isinstance(next_val, Task) else Task.of(next_val, name=target_name)

                final_ctx, final_res = await next_task._comp(next_ctx)

                if isinstance(final_res, Exception):
                    if emit_step:
                        emit_step(target_name, "failure")
                    return final_ctx, final_res

                if emit_step:
                    emit_step(target_name, "success")
                return final_ctx, final_res

            except Exception as e:
                if emit_step:
                    emit_step(target_name, "failure")
                return next_ctx, e

        # new_task сохраняет имя пайплайна self.name
        new_task: Task[U] = Task(name=self.name, computation=comp)
        new_task._inherit(self)
        return new_task

    # --- Functor Map ---
    def map(self, fn: Callable[[T], U]) -> Task[U]:
        return self.bind(lambda val: Task.of(fn(val)), step_name=f"Map({_extract_name(fn)})")

    # --- Tap / <* (побочный эффект с сохранением левого значения) ---
    def tap(self, effect: Union[Task[Any], Callable[..., Any]], step_name: Optional[str] = None) -> Task[T]:
        target_name = step_name or f"Tap({_extract_name(effect)})"

        async def comp(ctx: TaskContext) -> Tuple[TaskContext, Union[T, Exception]]:
            next_ctx, res = await self._comp(ctx)
            if isinstance(res, Exception):
                return next_ctx, res

            emit_step = next_ctx.get_meta("emit_step")
            if emit_step:
                emit_step(target_name, "running")

            try:
                if isinstance(effect, Task):
                    effect_task = effect
                else:
                    try:
                        sig = inspect.signature(effect)
                        eff_res = effect() if len(sig.parameters) == 0 else effect(res)
                    except (ValueError, TypeError):
                        eff_res = effect(res)

                    effect_task = eff_res if isinstance(eff_res, Task) else Task.of(eff_res)

                next_ctx, err = await effect_task._comp(next_ctx)
                if isinstance(err, Exception):
                    if emit_step:
                        emit_step(target_name, "failure")
                    return next_ctx, err

                if emit_step:
                    emit_step(target_name, "success")

            except Exception as e:
                if emit_step:
                    emit_step(target_name, "failure")
                return next_ctx, e

            return next_ctx, res

        # new_task сохраняет имя пайплайна self.name
        new_task: Task[T] = Task(name=self.name, computation=comp)
        new_task._inherit(self)
        return new_task

    # --- Перегрузка операторов >> и << ---
    def __rshift__(self, target: Union[Task[U], Callable[[T], Union[Task[U], U]]]) -> Task[U]:
        step_name = _extract_name(target)
        if isinstance(target, Task):
            return self.bind(lambda _: target, step_name=step_name)
        return self.bind(target, step_name=step_name)

    def __lshift__(self, effect: Union[Task[Any], Callable[..., Any]]) -> Task[T]:
        step_name = f"Tap({_extract_name(effect)})"
        return self.tap(effect, step_name=step_name)

    # --- Монадическое ветвление ---
    def if_else(
        self,
        predicate: Callable[[T], Union[bool, Coroutine[Any, Any, bool]]],
        then_branch: Union[Task[U], Callable[[T], Task[U]]],
        else_branch: Union[Task[U], Callable[[T], Task[U]]],
    ) -> Task[U]:
        def selector(val: T) -> Task[U]:
            async def comp(ctx: TaskContext) -> Tuple[TaskContext, Union[U, Exception]]:
                try:
                    cond = await _resolve_val(predicate(val))
                    chosen = then_branch if cond else else_branch
                    branch_task = chosen if isinstance(chosen, Task) else chosen(val)
                    return await branch_task._comp(ctx)
                except Exception as e:
                    return ctx, e

            return Task(name="IfElseBranch", computation=comp)

        return self.bind(selector, step_name="Condition(if_else)")

    # --- Параллельное выполнение ---
    @classmethod
    def parallel(
        cls,
        *tasks_or_factories: Union[Task[Any], Callable[[TaskContext], Task[Any]]],
        name: Optional[str] = None,
    ) -> Task[List[Any]]:
        group_name = name or "ParallelGroup"

        async def comp(ctx: TaskContext) -> Tuple[TaskContext, Union[List[Any], Exception]]:
            emit_step = ctx.get_meta("emit_step")

            tasks: List[Task[Any]] = []
            for item in tasks_or_factories:
                tasks.append(item if isinstance(item, Task) else item(ctx))

            async def safe_exec(t: Task[Any]) -> Tuple[TaskContext, Any]:
                try:
                    if emit_step:
                        emit_step(t.name, "running")
                    sub_ctx, val = await t._comp(ctx)
                    if emit_step:
                        status = "failure" if isinstance(val, Exception) else "success"
                        emit_step(t.name, status)
                    return sub_ctx, val
                except Exception as e:
                    if emit_step:
                        emit_step(t.name, "failure")
                    return ctx, e

            raw_results = await asyncio.gather(
                *(safe_exec(t) for t in tasks),
                return_exceptions=True,
            )

            collected: List[Any] = []
            merged_ctx = ctx

            for res_entry in raw_results:
                if isinstance(res_entry, BaseException):
                    return merged_ctx, res_entry if isinstance(res_entry, Exception) else Exception(str(res_entry))

                sub_ctx, val = res_entry
                if isinstance(val, Exception):
                    return merged_ctx, val

                merged_ctx = merged_ctx.update(sub_ctx.data)
                collected.append(val)

            return merged_ctx, collected

        parallel_task: Task[List[Any]] = Task(name=group_name, computation=comp)
        return parallel_task

    # --- Планирование ---
    def when(self, config_fn: Union[Schedule, Callable[[Schedule], Schedule]]) -> Task[T]:
        sched = Schedule()
        if callable(config_fn):
            res = config_fn(sched)
            self.schedule_config = res if isinstance(res, Schedule) else sched
        elif isinstance(config_fn, Schedule):
            self.schedule_config = config_fn
        return self

    @property
    def every(self) -> SchedulePropertyBridge[T]:
        return SchedulePropertyBridge(self)

    # --- Терминальные хуки ---
    def success(self, hook: Callable[..., Any]) -> Task[T]:
        self._success_hooks.append(hook)
        return self

    def error(self, hook: Callable[..., Any]) -> Task[T]:
        self._error_hooks.append(hook)
        return self

    def always(self, hook: Callable[..., Any]) -> Task[T]:
        """Хук, гарантированно выполняющийся всегда (аналог finally)."""
        self._finally_hooks.append(hook)
        return self

    def finally_(self, hook: Callable[..., Any]) -> Task[T]:
        """Алиас для .always(hook)."""
        return self.always(hook)

    # --- Runner ---
    async def run(self, initial_ctx: Optional[TaskContext] = None) -> Tuple[TaskContext, Union[T, Exception]]:
        ctx = initial_ctx or TaskContext()
        final_ctx, result = await self._comp(ctx)

        try:
            if isinstance(result, Exception):
                for err_hook in self._error_hooks:
                    await _invoke_hook(err_hook, result, final_ctx)
            else:
                for succ_hook in self._success_hooks:
                    await _invoke_hook(succ_hook, result, final_ctx)
        finally:
            for fin_hook in self._finally_hooks:
                await _invoke_hook(fin_hook, result, final_ctx)

        return final_ctx, result

    # --- Сериализация ---
    @classmethod
    def from_yaml(cls, source: Union[str, Any]) -> Task[Any]:
        from taskmonad.serialization import build_task_from_yaml
        return build_task_from_yaml(source)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task[Any]:
        from taskmonad.serialization import build_task_from_dict
        return build_task_from_dict(data)

    def _inherit(self, source: Task[Any]):
        self._success_hooks = source._success_hooks.copy()
        self._error_hooks = source._error_hooks.copy()
        self._finally_hooks = source._finally_hooks.copy()
        self.schedule_config = source.schedule_config