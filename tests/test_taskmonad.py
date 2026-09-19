import asyncio
import pytest
from taskmonad import Task, TaskContext, Schedule

# =====================================================================
# 1. ТЕСТЫ МОНАДИЧЕСКИХ ЗАКОНОВ (Monad Laws)
# =====================================================================

@pytest.mark.asyncio
async def test_monad_law_left_identity():
    """Law 1: Task.of(x).bind(f) == f(x)"""
    x = 10
    f = lambda val: Task.of(val * 3)

    _, res1 = await Task.of(x).bind(f).run()
    _, res2 = await f(x).run()

    assert res1 == res2 == 30

@pytest.mark.asyncio
async def test_monad_law_right_identity():
    """Law 2: m.bind(Task.of) == m"""
    m = Task.of(42)

    _, res1 = await m.bind(Task.of).run()
    _, res2 = await m.run()

    assert res1 == res2 == 42

@pytest.mark.asyncio
async def test_monad_law_associativity():
    """Law 3: m.bind(f).bind(g) == m.bind(lambda x: f(x).bind(g))"""
    m = Task.of(5)
    f = lambda x: Task.of(x + 10)
    g = lambda x: Task.of(x * 2)

    _, res1 = await (m.bind(f).bind(g)).run()
    _, res2 = await m.bind(lambda x: f(x).bind(g)).run()

    assert res1 == res2 == 30


# =====================================================================
# 2. ОПЕРАТОРЫ >> И << (BIND, AUTO-LIFT, TAP)
# =====================================================================

@pytest.mark.asyncio
async def test_rshift_with_plain_function():
    """Оператор >> должен автоматически оборачивать обычную функцию в Task."""
    task = Task.of(10) >> (lambda x: x + 5) >> (lambda x: x * 2)
    _, res = await task.run()
    assert res == 30

@pytest.mark.asyncio
async def test_rshift_with_async_function():
    """Оператор >> должен поддерживать асинхронные функции без явного Task."""
    async def async_add(x: int) -> int:
        await asyncio.sleep(0.01)
        return x + 20

    task = Task.of(5) >> async_add
    _, res = await task.run()
    assert res == 25

@pytest.mark.asyncio
async def test_rshift_with_direct_task():
    """Оператор >> при передаче Task игнорирует входящий аргумент и переходит к новому таску."""
    task = Task.of("initial") >> Task.of("replaced")
    _, res = await task.run()
    assert res == "replaced"

@pytest.mark.asyncio
async def test_lshift_tap_preserves_left_value():
    """Оператор << выполняет побочный эффект, но сохраняет результат левой стороны."""
    side_effect_executed = False

    def do_side_effect(val):
        nonlocal side_effect_executed
        side_effect_executed = True

    task = Task.of("my_data") << do_side_effect >> (lambda x: f"processed_{x}")
    _, res = await task.run()

    assert side_effect_executed is True
    assert res == "processed_my_data"

@pytest.mark.asyncio
async def test_lshift_tap_with_zero_arg_task():
    """Оператор << должен поддерживать передачу готового Task (без параметров)."""
    cleaned = False

    def cleanup():
        async def comp(ctx):
            nonlocal cleaned
            cleaned = True
            return ctx, None
        return Task(computation=comp)

    task = Task.of(100) << cleanup() >> (lambda x: x + 1)
    _, res = await task.run()

    assert cleaned is True
    assert res == 101


# =====================================================================
# 3. ОБРАБОТКА ОШИБОК И SHORT-CIRCUIT
# =====================================================================

@pytest.mark.asyncio
async def test_short_circuit_on_error():
    """При падении шага последующие шаги НЕ должны вызываться."""
    step2_called = False

    def failing_step(x):
        raise ValueError("Boom!")

    def step2(x):
        nonlocal step2_called
        step2_called = True
        return x

    task = Task.of(1) >> failing_step >> step2
    ctx, res = await task.run()

    assert isinstance(res, ValueError)
    assert str(res) == "Boom!"
    assert step2_called is False

@pytest.mark.asyncio
async def test_error_in_tap_breaks_pipeline():
    """Если побочный эффект в << падает, пайплайн должен прерываться."""
    def bad_cleanup(x):
        raise RuntimeError("Cleanup failed")

    task = Task.of("payload") << bad_cleanup >> (lambda x: "never_reached")
    _, res = await task.run()

    assert isinstance(res, RuntimeError)

@pytest.mark.asyncio
async def test_hooks_success_and_error():
    """Хуки .success() и .error() должны корректно срабатывать."""
    success_received = None
    error_received = None

    ok_pipeline = (
        Task("OKPipeline")
        .success(lambda res, ctx: setattr(pytest, "_succ", res))
        >> (lambda _: "finished")
    )
    await ok_pipeline.run()
    assert getattr(pytest, "_succ") == "finished"

    fail_pipeline = (
        Task("FailPipeline")
        .error(lambda err, ctx: setattr(pytest, "_err", str(err)))
        # pyrefly: ignore [division-by-zero]
        >> (lambda _: 1 / 0)
    )
    await fail_pipeline.run()
    assert "division by zero" in getattr(pytest, "_err")


# =====================================================================
# 4. МОНАДИЧЕСКОЕ ВЕТВЛЕНИЕ (IF / ELSE)
# =====================================================================

@pytest.mark.asyncio
async def test_if_else_branch_true():
    """Ветвление: срабатывание then_branch."""
    task = Task.of(15).if_else(
        predicate=lambda x: x > 10,
        then_branch=lambda x: Task.of(f"high: {x}"),
        else_branch=lambda x: Task.of(f"low: {x}"),
    )
    _, res = await task.run()
    assert res == "high: 15"

@pytest.mark.asyncio
async def test_if_else_branch_false():
    """Ветвление: срабатывание else_branch."""
    task = Task.of(3).if_else(
        predicate=lambda x: x > 10,
        then_branch=lambda x: Task.of("high"),
        else_branch=lambda x: Task.of("low"),
    )
    _, res = await task.run()
    assert res == "low"

@pytest.mark.asyncio
async def test_if_else_async_predicate():
    """Ветвление: поддержка асинхронного предиката."""
    async def async_is_even(n: int) -> bool:
        await asyncio.sleep(0.01)
        return n % 2 == 0

    task = Task.of(4).if_else(
        predicate=async_is_even,
        then_branch=Task.of("even"),
        else_branch=Task.of("odd"),
    )
    _, res = await task.run()
    assert res == "even"


# =====================================================================
# 5. ПАРАЛЛЕЛЬНЫЕ ВЫЧИСЛЕНИЯ (PARALLEL / GATHER)
# =====================================================================

@pytest.mark.asyncio
async def test_parallel_success_and_gather():
    """Task.parallel выполняет ветки конкурентно и собирает результаты в список."""
    async def task_a(ctx):
        await asyncio.sleep(0.05)
        return ctx.set("a", 1), 10

    async def task_b(ctx):
        await asyncio.sleep(0.02)
        return ctx.set("b", 2), 20

    task = Task.parallel(
        Task(computation=task_a),
        Task(computation=task_b)
    )
    ctx, res = await task.run()

    assert res == [10, 20]
    assert ctx.get("a") == 1
    assert ctx.get("b") == 2

@pytest.mark.asyncio
async def test_parallel_fail_fast():
    """Если одна из параллельных веток падает, весь Parallel завершается ошибкой."""
    async def bad_task(ctx):
        raise TimeoutError("Network timeout")

    task = Task.parallel(
        Task.of("ok"),
        Task(computation=bad_task)
    )
    _, res = await task.run()

    assert isinstance(res, TimeoutError)


# =====================================================================
# 6. КОНТЕКСТ ВЫПОЛНЕНИЯ (TASKCONTEXT)
# =====================================================================

@pytest.mark.asyncio
async def test_context_immutability():
    """Контекст должен быть неизменяемым (возвращать новый инстанс при модификациях)."""
    ctx1 = TaskContext(data={"foo": 1})
    ctx2 = ctx1.set("foo", 2)

    assert ctx1.get("foo") == 1
    assert ctx2.get("foo") == 2
    assert ctx1 is not ctx2

@pytest.mark.asyncio
async def test_context_state_passing():
    """Контекст накапливает состояние по цепочке шагов."""
    def step1():
        async def comp(ctx):
            return ctx.set("user_id", 42), "user_ok"
        return Task(computation=comp)

    def step2():
        async def comp(ctx):
            uid = ctx.get("user_id")
            return ctx.set("role", "admin"), f"role_for_{uid}"
        return Task(computation=comp)

    task = step1() >> (lambda _: step2())
    ctx, res = await task.run()

    assert ctx.get("user_id") == 42
    assert ctx.get("role") == "admin"
    assert res == "role_for_42"


# =====================================================================
# 7. ЧЕЛОВЕКОПОНЯТНОЕ РАСПИСАНИЕ (SCHEDULE)
# =====================================================================

def test_schedule_fluent_builder():
    """Проверка человекопонятного расписания и экспорта в словарь."""
    sched = Schedule().daily().at("14:30")
    d = sched.to_dict()
    assert d["unit"] == "day"
    assert d["every"] == 1
    assert d["at"] == "14:30"

    sched_custom = Schedule().every(15).minutes()
    assert sched_custom.interval_unit == "minute"
    assert sched_custom.interval_value == 15

    sched_weekdays = Schedule().weekly().on("monday", "friday").at("09:00")
    assert "monday" in sched_weekdays.weekdays
    assert "friday" in sched_weekdays.weekdays

def test_task_schedule_integration():
    """Проверка методов Task.when и Task.every."""
    task1 = Task("T1").when(lambda do: do.hourly())
    assert task1.schedule_config.interval_unit == "hour"

    task2 = Task("T2").every.day
    assert task2.schedule_config.interval_unit == "day"

    task3 = Task("T3").every.minutes(10)
    assert task3.schedule_config.interval_unit == "minute"
    assert task3.schedule_config.interval_value == 10


# =====================================================================
# 8. QT BRIDGE (ИНТЕГРАЦИЯ С PYQT6 БЕЗ GUI-ОКНА)
# =====================================================================

def test_qt_runner_thread(qapp=None):
    """
    Проверка TaskRunnerThread и эмиссии сигналов.
    Если PyQt6 установлен, тест проверяет перехват сигналов потока.
    """
    try:
        from PyQt6.QtCore import QCoreApplication
        from taskmonad.qt_bridge import TaskRunnerThread
    except ImportError:
        pytest.skip("PyQt6 не установлен, пропускаем тест Qt Bridge")

    # Инициализируем минимальный headless QCoreApplication если нет
    app = QCoreApplication.instance() or QCoreApplication([])

    logs = []
    statuses = []

    task = (
        Task.of("hello")
        >> (lambda s: f"{s} world")
    )

    runner = TaskRunnerThread(task)
    runner.signals.step_executed.connect(lambda name, st: statuses.append((name, st)))

    runner.start()
    runner.wait(3000)  # Ждем завершения потока

    assert runner.isFinished()