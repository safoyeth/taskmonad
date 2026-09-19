# TaskMonad Architecture

`taskmonad` is a monadic pipeline and asynchronous task execution framework for Python. It blends functional programming paradigms (Monads, Functors, and Applicative Taps) with Python's asynchronous ecosystem (`asyncio`) and desktop GUI frameworks (PyQt / PySide).

---

## 1. Core Principles

Traditional asynchronous workflow scripts in Python frequently suffer from:
- **Pyramid of callbacks or nested try/except blocks**, leading to unreadable error handling.
- **Accidental mutable state leakage**, where concurrent steps mutate global or shared dictionaries.
- **GUI freezing and boilerplate threading**, when bridging async IO operations with Qt signals and widgets.
- **Tight coupling**, making dynamic reconfiguration (e.g. from YAML or JSON manifests) difficult.

TaskMonad addresses these issues using pure functional programming constructs adapted for Python.

```
       [ Upstream Task ]
               │
          >> (bind)
               ▼
   Does upstream have error?
        ├── YES ──► Short-circuit (Propagate Exception)
        └── NO  ──► Pass value to Next Step (Task or Callable)
                         │
                    << (tap)
                         ▼
        Execute Side-effect (logs, cleanup)
        Preserve incoming value unchanged!
```

---

## 2. The Monad Concept in TaskMonad

A **Monad** in TaskMonad is encapsulated by the generic `Task[T]` class. It wraps an asynchronous computation:

$$\text{Computation} : \text{TaskContext} \to \text{Coroutine}[\text{Tuple}[\text{TaskContext}, T \cup \text{Exception}]]$$

### 2.1 The Three Monad Laws

`taskmonad` strictly adheres to mathematical Monad Laws, verified by the automated test suite in `tests/test_taskmonad.py`:

#### 1. Left Identity
Wrapping a value into a monadic task and binding a function $f$ is equivalent to applying $f$ to the value directly:
$$\text{Task.of}(x).\text{bind}(f) \equiv f(x)$$

```python
x = 10
f = lambda val: Task.of(val * 3)

res1 = await Task.of(x).bind(f).run()
res2 = await f(x).run()
assert res1[1] == res2[1] == 30
```

#### 2. Right Identity
Binding a task to the unit constructor `Task.of` leaves the task unaltered:
$$m.\text{bind}(\text{Task.of}) \equiv m$$

```python
m = Task.of(42)
res1 = await m.bind(Task.of).run()
res2 = await m.run()
assert res1[1] == res2[1] == 42
```

#### 3. Associativity
Chaining bindings in sequence behaves identically regardless of how they are grouped:
$$m.\text{bind}(f).\text{bind}(g) \equiv m.\text{bind}(\lambda x. f(x).\text{bind}(g))$$

```python
m = Task.of(5)
f = lambda x: Task.of(x + 10)
g = lambda x: Task.of(x * 2)

res1 = await (m.bind(f).bind(g)).run()
res2 = await m.bind(lambda x: f(x).bind(g)).run()
assert res1[1] == res2[1] == 30
```

---

## 3. Short-Circuiting Error Model

When a computation in the pipeline raises an exception or returns an instance of `Exception`, TaskMonad intercepts it:

1. **Short-Circuiting**: Any subsequent steps chained via `bind` (`>>`), `map`, or `tap` (`<<`) are immediately skipped.
2. **Safety**: No unhandled exceptions crash the running event loop unexpectedly; errors are encapsulated as computation results `(ctx, exception)`.
3. **Terminal Error Hooks**: If `.error(hook)` was registered on the pipeline, the hook is triggered with `(exception, final_context)`.
4. **GUI Notification**: When running inside `TaskRunnerThread`, the `failed` Qt signal emits the error message to the UI thread.

```python
def failing_step(x):
    raise ValueError("Invalid payload")

def unreachable_step(x):
    print("This will never be called")
    return x * 2

task = Task.of(10) >> failing_step >> unreachable_step
ctx, result = await task.run()

assert isinstance(result, ValueError)
```

---

## 4. State Immutability: `TaskContext`

`TaskContext` is a frozen dataclass holding two distinct namespaces:

| Namespace | Deep-copied on mutation? | Target Usage |
| :--- | :--- | :--- |
| `data` | **Yes** (via `copy.deepcopy`) | Business payload, domain state, intermediate calculations |
| `meta` | **No** (shallow copy) | Non-serializable handles: Qt signal callbacks, system loggers, cancellation tokens |

### Why Deepcopy for `data`?
Because tasks can be executed concurrently via `Task.parallel`. Deep-copying guarantees that one parallel branch cannot accidentally mutate a list or dictionary used by another concurrent branch.

```python
ctx1 = TaskContext(data={"count": 1})
ctx2 = ctx1.set("count", 2)

assert ctx1.get("count") == 1
assert ctx2.get("count") == 2
assert ctx1 is not ctx2
```

---

## 5. Parallelism and Concurrency

`Task.parallel` executes multiple tasks concurrently using `asyncio.gather(*, return_exceptions=True)`.

- **Fail-Fast**: If any task fails, the first exception encountered short-circuits the result.
- **Context Merging**: If all parallel branches succeed, their individual `data` dictionaries are merged into a unified `TaskContext`, and the return values are aggregated into a list: `[val_1, val_2, ...]`.
- **Step Tracking**: Each parallel branch automatically emits `"running"` and `"success"` / `"failure"` signals to Qt.

---

## 6. Real-Time Qt Signal Bridge

Desktop applications using PyQt6, PyQt5, or PySide6 must never block the main GUI thread.

`TaskRunnerThread` inherits from `QThread`:
1. Spawns an isolated background OS thread.
2. Instantiates a dedicated `asyncio` event loop.
3. Injects `emit_step` and `emit_log` callbacks into `ctx.meta`.
4. Dispatches Qt signals across thread boundaries (`started`, `step_executed`, `log`, `finished`, `failed`).
5. Reliably closes the event loop upon task termination.
