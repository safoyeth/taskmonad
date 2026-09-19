# Pipeline Composition Guide

This guide walks through composing, executing, and orchestrating pipelines using `taskmonad`.

---

## 1. Creating Atomic Tasks

There are two primary ways to create tasks:

### 1.1 `Task.of(value)`
Creates a task containing an existing value or coroutine:
```python
from taskmonad import Task

# Wraps a synchronous value
task = Task.of(42, name="InitialNumber")

# Wraps a coroutine
async def fetch_token():
    return "secret-token-xyz"

token_task = Task.of(fetch_token(), name="FetchToken")
```

### 1.2 Custom Computation: `Task(name, computation)`
When a step needs direct access to `TaskContext`:
```python
from taskmonad import Task, TaskContext

async def calculate_hash(ctx: TaskContext):
    user_id = ctx.get("user_id")
    computed_hash = f"HASH_{user_id}"
    
    # Return (updated_context, result_value)
    return ctx.set("user_hash", computed_hash), computed_hash

task = Task(name="ComputeHash", computation=calculate_hash)
```

---

## 2. Sequential Composition: The `>>` Operator

The `>>` operator binds tasks together. `taskmonad` automatically lifts different types of functions:

### 2.1 Binding a Plain Synchronous Function
```python
pipeline = (
    Task.of(10)
    >> (lambda x: x + 5)       # Plain function: 15
    >> (lambda x: x * 2)       # Plain function: 30
    >> (lambda x: f"Res: {x}") # Plain function: "Res: 30"
)
```

### 2.2 Binding an Asynchronous Coroutine Function
```python
import asyncio

async def fetch_user_data(user_id: int) -> dict:
    await asyncio.sleep(0.1)
    return {"id": user_id, "name": "Alice"}

pipeline = Task.of(1) >> fetch_user_data
```

### 2.3 Binding a Function that Returns a `Task`
```python
def process_order(item_id: str) -> Task[str]:
    async def comp(ctx: TaskContext):
        return ctx, f"ORDER_FOR_{item_id}"
    return Task(name=f"Order({item_id})", computation=comp)

pipeline = Task.of("item-123") >> process_order
```

### 2.4 Sequencing Two `Task` Instances Directly
When the target on the right-hand side is already a `Task`, the upstream value is ignored while context state is preserved:
```python
step1 = Task.of("first")
step2 = Task.of("second")

pipeline = step1 >> step2  # Output: "second"
```

---

## 3. Side-Effects: The `<<` (Tap) Operator

The `<<` operator executes a side-effect (e.g. audit logging, cleanup, caching, disk synchronization) **without changing the upstream value** flowing downstream.

```python
def cleanup_temp_files(filepaths: list[str]):
    # Deletes temporary files from disk
    for f in filepaths:
        Path(f).unlink(missing_ok=True)

pipeline = (
    Task.of("data_report.csv")
    << (lambda path: print(f"Processing report at {path}...")) # Tap with 1 argument
    >> generate_report
    << cleanup_temp_files                                     # Cleans up files
    >> send_email_notification                                # Receives report from generate_report!
)
```

> [!NOTE]
> If a side-effect in `<<` raises an exception, the pipeline will short-circuit and fail.

---

## 4. Conditional Branching: `if_else`

`Task.if_else` provides functional conditional routing based on synchronous or asynchronous predicates.

```python
def route_payment(amount: float):
    return (
        Task.of(amount).if_else(
            predicate=lambda val: val > 10_000,
            then_branch=lambda val: Task.of(f"Routed to manual KYC: ${val}"),
            else_branch=lambda val: Task.of(f"Processed automatically: ${val}"),
        )
    )
```

Async predicates are fully supported:
```python
async def check_inventory(product_id: str) -> bool:
    await asyncio.sleep(0.05)
    return True

pipeline = (
    Task.of("PROD-999")
    .if_else(
        predicate=check_inventory,
        then_branch=Task.of("In Stock"),
        else_branch=Task.of("Out of Stock"),
    )
)
```

---

## 5. Concurrency: `Task.parallel`

`Task.parallel` executes multiple independent tasks simultaneously using `asyncio.gather`.

```python
import asyncio
from taskmonad import Task, TaskContext

def download_source(url: str):
    async def comp(ctx: TaskContext):
        await asyncio.sleep(0.2)
        return ctx.set(f"downloaded_{url}", True), f"Data from {url}"
    return Task(name=f"Download({url})", computation=comp)

pipeline = (
    Task.parallel(
        download_source("https://api.one.com"),
        download_source("https://api.two.com"),
        download_source("https://api.three.com"),
    )
    >> (lambda results: "\n---\n".join(results))
)

ctx, report = await pipeline.run()
```

- Results are returned as a list matching the order of input tasks.
- If any task raises an exception, the parallel step stops and immediately propagates the error.

---

## 6. Scheduling Configuration

You can attach execution triggers directly to any `Task` instance:

### Fluent Schedule Property Bridge
```python
# Run every 5 seconds
task = Task("Worker").every.seconds(5)

# Run every 200 milliseconds
task = Task("FastPoller").every.milliseconds(200)

# Run hourly or daily
task = Task("DailyJob").every.day
```

### Explicit `Schedule` Object
```python
from taskmonad import Schedule

task = Task("ComplexSchedule").when(
    lambda s: s.weekly().on("monday", "friday").at("08:30")
)
```

---

## 7. Terminal Callbacks: `success`, `error`, and `always` / `finally_`

Terminal lifecycle hooks allow you to register callback functions that are guaranteed to run when the pipeline completes:

| Hook Method | Invocation Condition | Callback Signature |
| :--- | :--- | :--- |
| `.success(hook)` | Only when the pipeline succeeds without error | `(result, ctx)` or `(result)` or `()` |
| `.error(hook)` | When an unhandled error or short-circuit occurs | `(exception, ctx)` or `(exception)` or `()` |
| `.always(hook)` *(alias `.finally_(hook)`)* | **Always**, regardless of success or failure | `(result_or_err, ctx)` or `(result_or_err)` or `()` |

Hooks support both synchronous functions and asynchronous coroutines (`async def`).

```python
async def cleanup_database_connections(res_or_err, ctx):
    print("Closing pooled database connections...")

pipeline = (
    Task("ProductionPipeline")
    .success(lambda result, ctx: print(f"✅ Success! Output: {result}"))
    .error(lambda err, ctx: print(f"🚨 Failure: {err}"))
    .always(cleanup_database_connections)  # <--- Guaranteed execution always!
    >> validate_input
    >> execute_pipeline
)

await pipeline.run()
```

---

## 8. Architectural Rule: Hooks First, Composition Second!

> [!IMPORTANT]
> **CRITICAL ARCHITECTURAL RULE:**  
> **Lifecycle hooks (`.success()`, `.error()`, `.always()`, `.finally_()`) and scheduling configurations (`.when()`, `.every`) MUST be declared on the root task BEFORE chaining steps with `>>` and `<<` operators!**

### Why is this required?

In TaskMonad, the pipeline is constructed as an immutable computation chain. Each monadic operator (`>>`, `<<`, `map`) instantiates a new `Task` and copies configuration from the left operand via an internal inheritance mechanism (`_inherit(self)`):

```
[ Root Task ]  <─── Define .success(), .error(), .always(), .when() HERE
      │
      ├── (copies hooks via _inherit)
      ▼
   Step 1 (>>)
      │
      ├── (copies hooks via _inherit)
      ▼
   Step 2 (>>) ──► The final pipeline holds all hooks and executes them on run()!
```

### Examples: Do's and Don'ts

```python
# ✅ CORRECT PATTERN: Declare hooks on the root, then bind
pipeline = (
    Task("DataSync")
    .success(on_success)
    .error(on_error)
    .always(cleanup)
    >> fetch_data
    >> process_data
    >> save_data
)

# ❌ INCORRECT PATTERN: Attempting to attach hooks to root AFTER binding
root = Task("DataSync")
pipeline = root >> fetch_data >> process_data
root.always(cleanup)  # ERROR: pipeline already inherited an empty hooks list!
```
