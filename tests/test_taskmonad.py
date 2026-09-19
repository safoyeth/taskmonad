import asyncio
import pytest
from taskmonad import Task, TaskContext, Schedule, ActionRegistry, action

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
    task = Task.of(10) >> (lambda x: x + 5) >> (lambda x: x * 2)
    _, res = await task.run()
    assert res == 30

@pytest.mark.asyncio
async def test_rshift_with_async_function():
    async def async_add(x: int) -> int:
        await asyncio.sleep(0.01)
        return x + 20

    task = Task.of(5) >> async_add
    _, res = await task.run()
    assert res == 25

@pytest.mark.asyncio
async def test_rshift_with_direct_task():
    task = Task.of("initial") >> Task.of("replaced")
    _, res = await task.run()
    assert res == "replaced"

@pytest.mark.asyncio
async def test_lshift_tap_preserves_left_value():
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
    cleaned = False

    def cleanup():
        async def comp(ctx):
            nonlocal cleaned
            cleaned = True
            return ctx, None
        return Task(name="CleanupTask", computation=comp)

    task = Task.of(100) << cleanup() >> (lambda x: x + 1)
    _, res = await task.run()

    assert cleaned is True
    assert res == 101


# =====================================================================
# 3. ИЗОЛЯЦИЯ ОШИБОК И SHORT-CIRCUIT
# =====================================================================

@pytest.mark.asyncio
async def test_short_circuit_on_error():
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
    def bad_cleanup(x):
        raise RuntimeError("Cleanup failed")

    task = Task.of("payload") << bad_cleanup >> (lambda x: "never_reached")
    _, res = await task.run()

    assert isinstance(res, RuntimeError)

@pytest.mark.asyncio
async def test_hooks_success_and_error():
    success_val = None
    error_val = None

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
    task = Task.of(15).if_else(
        predicate=lambda x: x > 10,
        then_branch=lambda x: Task.of(f"high: {x}"),
        else_branch=lambda x: Task.of(f"low: {x}"),
    )
    _, res = await task.run()
    assert res == "high: 15"

@pytest.mark.asyncio
async def test_if_else_branch_false():
    task = Task.of(3).if_else(
        predicate=lambda x: x > 10,
        then_branch=lambda x: Task.of("high"),
        else_branch=lambda x: Task.of("low"),
    )
    _, res = await task.run()
    assert res == "low"

@pytest.mark.asyncio
async def test_if_else_async_predicate():
    async def async_is_even(n: int) -> bool:
        await asyncio.sleep(0.005)
        return n % 2 == 0

    task = Task.of(4).if_else(
        predicate=async_is_even,
        then_branch=Task.of("even"),
        else_branch=Task.of("odd"),
    )
    _, res = await task.run()
    assert res == "even"


# =====================================================================
# 5. ПАРАЛЛЕЛИЗМ (PARALLEL / GATHER)
# =====================================================================

@pytest.mark.asyncio
async def test_parallel_success_and_gather():
    async def task_a(ctx):
        await asyncio.sleep(0.01)
        return ctx.set("a", 1), 10

    async def task_b(ctx):
        await asyncio.sleep(0.01)
        return ctx.set("b", 2), 20

    task = Task.parallel(
        Task(name="TaskA", computation=task_a),
        Task(name="TaskB", computation=task_b)
    )
    ctx, res = await task.run()

    assert res == [10, 20]
    assert ctx.get("a") == 1
    assert ctx.get("b") == 2

@pytest.mark.asyncio
async def test_parallel_fail_fast():
    async def bad_task(ctx):
        raise TimeoutError("Network timeout")

    task = Task.parallel(
        Task.of("ok", name="OkTask"),
        Task(name="BadTask", computation=bad_task)
    )
    _, res = await task.run()

    assert isinstance(res, TimeoutError)


# =====================================================================
# 6. КОНТЕКСТ ВЫПОЛНЕНИЯ (TASKCONTEXT)
# =====================================================================

@pytest.mark.asyncio
async def test_context_immutability():
    ctx1 = TaskContext(data={"foo": 1})
    ctx2 = ctx1.set("foo", 2)

    assert ctx1.get("foo") == 1
    assert ctx2.get("foo") == 2
    assert ctx1 is not ctx2

@pytest.mark.asyncio
async def test_context_state_passing():
    def step1():
        async def comp(ctx):
            return ctx.set("user_id", 42), "user_ok"
        return Task(name="Step1", computation=comp)

    def step2():
        async def comp(ctx):
            uid = ctx.get("user_id")
            return ctx.set("role", "admin"), f"role_for_{uid}"
        return Task(name="Step2", computation=comp)

    task = step1() >> (lambda _: step2())
    ctx, res = await task.run()

    assert ctx.get("user_id") == 42
    assert ctx.get("role") == "admin"
    assert res == "role_for_42"


# =====================================================================
# 7. ЧЕЛОВЕКОПОНЯТНОЕ РАСПИСАНИЕ (SCHEDULE)
# =====================================================================

def test_schedule_all_granularity_modes():
    # Субсекунды и секунды
    s_ms = Schedule().every(250).milliseconds()
    assert s_ms.interval_unit == "milliseconds"
    assert s_ms.interval_value == 250

    s_sec = Schedule().every(15).seconds()
    assert s_sec.interval_unit == "seconds"
    assert s_sec.interval_value == 15

    # Разово
    s_once = Schedule().once("2026-12-31", "23:59:59")
    assert s_once.mode == "once"
    assert s_once.date == "2026-12-31"
    assert s_once.at_time == "23:59:59"

    # Дни месяца
    s_monthly = Schedule().monthly().on_days_of_month(1, 15).at("12:00")
    assert s_monthly.mode == "monthly"
    assert s_monthly.month_days == [1, 15]
    assert s_monthly.at_time == "12:00"

    # Cron
    s_cron = Schedule().cron("*/10 * * * *")
    assert s_cron.mode == "cron"
    assert s_cron.cron_expr == "*/10 * * * *"

    # Startup
    s_start = Schedule().on_startup()
    assert s_start.mode == "on_startup"

def test_task_property_bridge():
    t1 = Task("T1").every.seconds(5)
    assert t1.schedule_config.interval_unit == "seconds"
    assert t1.schedule_config.interval_value == 5

    t2 = Task("T2").every.milliseconds(100)
    assert t2.schedule_config.interval_unit == "milliseconds"
    assert t2.schedule_config.interval_value == 100


# =====================================================================
# 8. ДЕСЕРИАЛИЗАЦИЯ ИЗ YAML
# =====================================================================

@pytest.mark.asyncio
async def test_from_yaml_full_flow():
    ActionRegistry.clear()

    @action("add_ten")
    def add_ten(x: int = 0) -> int:
        return (x or 0) + 10

    @action("multiply_by_two")
    def multiply_by_two(x: int) -> int:
        return x * 2

    @action("side_logger")
    def side_logger(x: int) -> None:
        setattr(pytest, "_yaml_log", x)

    yaml_manifest = """
    name: "YamlTestPipeline"
    schedule:
      mode: "interval"
      every: 30
      unit: "seconds"
    pipeline:
      - type: "step"
        action: "add_ten"
      - type: "tap"
        action: "side_logger"
      - type: "step"
        action: "multiply_by_two"
    """

    task = Task.from_yaml(yaml_manifest)
    assert task.name == "YamlTestPipeline"
    assert task.schedule_config.interval_value == 30
    assert task.schedule_config.interval_unit == "seconds"

    _, result = await task.run()
    assert getattr(pytest, "_yaml_log") == 10
    assert result == 20


# =====================================================================
# 9. QT BRIDGE
# =====================================================================

def test_qt_runner_thread():
    try:
        from PyQt6.QtCore import QCoreApplication
        from taskmonad.qt_bridge import TaskRunnerThread
    except ImportError:
        pytest.skip("PyQt6 не установлен")

    app = QCoreApplication.instance() or QCoreApplication([])

    statuses = []
    task = Task.of("hello") >> (lambda s: f"{s} world")

    runner = TaskRunnerThread(task)
    runner.signals.step_executed.connect(lambda name, st: statuses.append((name, st)))

    runner.start()
    runner.wait(2000)

    assert runner.isFinished()